import json
import sys
from pathlib import Path
prefix = sys.argv[1]
f = json.loads(Path(f"cdk.out/{prefix}-foundation.template.json").read_text())
a = json.loads(Path(f"cdk.out/{prefix}-app.template.json").read_text())
def resources(t, kind):
    return [v.get("Properties", {}) for v in t["Resources"].values()
            if v["Type"] == kind]
assert not resources(f, "AWS::EC2::NatGateway")
repo = resources(f, "AWS::ECR::Repository")[0]
assert repo["ImageTagMutability"] == "IMMUTABLE"
assert "LifecyclePolicy" in repo
queues = resources(f, "AWS::SQS::Queue")
assert any(q.get("RedrivePolicy", {}).get("maxReceiveCount") == 3 for q in queues)
assert any(s.get("RawMessageDelivery") for s in resources(f, "AWS::SNS::Subscription"))
assert any("ReportBatchItemFailures" in m.get("FunctionResponseTypes", [])
           for m in resources(f, "AWS::Lambda::EventSourceMapping"))
task = resources(a, "AWS::ECS::TaskDefinition")[0]
assert task["ExecutionRoleArn"] != task["TaskRoleArn"]
assert resources(a, "AWS::ECS::Service")[0]["DesiredCount"] == 1
assert all(g.get("RetentionInDays") == 7 for t in (f,a)
           for g in resources(t, "AWS::Logs::LogGroup"))
print("Template assertions PASS")

# Policy checks: no world-open task port; least-privilege SNS publishing.
for group in resources(a, "AWS::EC2::SecurityGroup"):
    for rule in group.get("SecurityGroupIngress", []):
        if rule.get("FromPort") == 8080:
            assert "SourceSecurityGroupId" in rule
            assert "CidrIp" not in rule
policies = resources(a, "AWS::IAM::Policy")
statements = [s for p in policies for s in p["PolicyDocument"]["Statement"]]
publish = [s for s in statements if s.get("Action") == "sns:Publish"
           or "sns:Publish" in s.get("Action", [])]
assert publish and all(s["Resource"] != "*" for s in publish)
print("Security policy checks PASS")
