import os
import re
import aws_cdk as cdk
from aws_cdk import (
    aws_ec2 as ec2, aws_ecr as ecr, aws_ecs as ecs,
    aws_elasticloadbalancingv2 as elb, aws_logs as logs,
    aws_iam as iam, aws_sqs as sqs, aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
    aws_dynamodb as dynamodb, aws_lambda as lam,
    aws_lambda_event_sources as sources,
)

class Foundation(cdk.Stack):
    def __init__(self, scope, sid, **kwargs):
        super().__init__(scope, sid, **kwargs)
        self.vpc = ec2.Vpc(self, "Vpc", max_azs=2, nat_gateways=0,
            subnet_configuration=[ec2.SubnetConfiguration(
                name="public", subnet_type=ec2.SubnetType.PUBLIC,
                cidr_mask=24)])
        self.repo = ecr.Repository(self, "Repository",
            image_tag_mutability=ecr.TagMutability.IMMUTABLE,
            lifecycle_rules=[ecr.LifecycleRule(max_image_count=20)],
            removal_policy=cdk.RemovalPolicy.DESTROY,
            empty_on_delete=True)
        self.table = dynamodb.Table(self, "Results",
            partition_key=dynamodb.Attribute(
                name="eventId", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.DESTROY)
        self.dlq = sqs.Queue(self, "DLQ",
            retention_period=cdk.Duration.days(14),
            encryption=sqs.QueueEncryption.SQS_MANAGED)
        self.queue = sqs.Queue(self, "OrdersQueue",
            visibility_timeout=cdk.Duration.seconds(60),
            retention_period=cdk.Duration.days(4),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
            dead_letter_queue=sqs.DeadLetterQueue(
                queue=self.dlq, max_receive_count=3))
        self.topic = sns.Topic(self, "OrderEvents")
        self.topic.add_subscription(subscriptions.SqsSubscription(
            self.queue, raw_message_delivery=True))
        consumer_logs = logs.LogGroup(self, "ConsumerLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=cdk.RemovalPolicy.DESTROY)
        fn = lam.Function(self, "Consumer",
            runtime=lam.Runtime.PYTHON_3_12,
            handler="handler.handler", code=lam.Code.from_asset("consumer"),
            timeout=cdk.Duration.seconds(10), memory_size=128,
            log_group=consumer_logs,
            environment={"TABLE_NAME": self.table.table_name})
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["dynamodb:PutItem"],
            resources=[self.table.table_arn]))
        fn.add_event_source(sources.SqsEventSource(
            self.queue, batch_size=1, report_batch_item_failures=True))
        values = {"RepositoryUri": self.repo.repository_uri,
            "RepositoryName": self.repo.repository_name,
            "QueueUrl": self.queue.queue_url, "DLQUrl": self.dlq.queue_url,
            "TopicArn": self.topic.topic_arn,
            "TableName": self.table.table_name,
            "ConsumerName": fn.function_name,
            "ConsumerLogGroup": consumer_logs.log_group_name,
            "VpcId": self.vpc.vpc_id}
        for key, value in values.items():
            cdk.CfnOutput(self, key, value=value)

class Application(cdk.Stack):
    def __init__(self, scope, sid, foundation, image_tag, **kwargs):
        super().__init__(scope, sid, **kwargs)
        f = foundation
        cluster = ecs.Cluster(self, "Cluster", vpc=f.vpc)
        alb_sg = ec2.SecurityGroup(self, "AlbSG", vpc=f.vpc)
        alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80))
        task_sg = ec2.SecurityGroup(self, "TaskSG", vpc=f.vpc)
        task_sg.add_ingress_rule(alb_sg, ec2.Port.tcp(8080))
        execution = iam.Role(self, "ExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AmazonECSTaskExecutionRolePolicy")])
        task_role = iam.Role(self, "TaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"))
        f.topic.grant_publish(task_role)
        group = logs.LogGroup(self, "WebLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=cdk.RemovalPolicy.DESTROY)
        task = ecs.FargateTaskDefinition(self, "Task",
            cpu=256, memory_limit_mib=512,
            execution_role=execution, task_role=task_role,
            runtime_platform=ecs.RuntimePlatform(
                cpu_architecture=ecs.CpuArchitecture.X86_64,
                operating_system_family=ecs.OperatingSystemFamily.LINUX))
        container = task.add_container("web",
            image=ecs.ContainerImage.from_ecr_repository(f.repo, image_tag),
            environment={"APP_VERSION": image_tag,
                         "TOPIC_ARN": f.topic.topic_arn},
            logging=ecs.LogDrivers.aws_logs(stream_prefix="web",
                                            log_group=group))
        container.add_port_mappings(ecs.PortMapping(container_port=8080))
        alb = elb.ApplicationLoadBalancer(self, "Alb", vpc=f.vpc,
            internet_facing=True, security_group=alb_sg)
        listener = alb.add_listener("Http", port=80, open=False)
        service = ecs.FargateService(self, "Service", cluster=cluster,
            task_definition=task, desired_count=1,
            assign_public_ip=True, security_groups=[task_sg],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            min_healthy_percent=100, max_healthy_percent=200,
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
            health_check_grace_period=cdk.Duration.seconds(60))
        listener.add_targets("Targets", port=8080, targets=[service],
            health_check=elb.HealthCheck(path="/health", healthy_http_codes="200"),
            deregistration_delay=cdk.Duration.seconds(15))
        for key, value in {"ServiceUrl": "http://" + alb.load_balancer_dns_name,
            "ClusterName": cluster.cluster_name,
            "ServiceName": service.service_name,
            "WebLogGroup": group.log_group_name}.items():
            cdk.CfnOutput(self, key, value=value)

app = cdk.App()
prefix = app.node.try_get_context("prefix") or "sis3-dev"
if not re.fullmatch(r"[a-z][a-z0-9-]{2,24}", prefix):
    raise ValueError("prefix: 3-25 lowercase letters, digits, hyphens")
tag = app.node.try_get_context("image_tag") or "not-deployed"
env = cdk.Environment(account=os.environ["CDK_DEFAULT_ACCOUNT"],
    region=os.environ.get("CDK_DEFAULT_REGION", "eu-north-1"))
f = Foundation(app, prefix + "-foundation", env=env)
Application(app, prefix + "-app", foundation=f, image_tag=tag, env=env)
cdk.Tags.of(app).add("Project", "SIS3")
cdk.Tags.of(app).add("Environment", prefix)
app.synth()
