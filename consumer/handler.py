import json
import os
import boto3
from botocore.exceptions import ClientError

table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])

def handler(event, context):
    failures = []
    for record in event["Records"]:
        try:
            data = json.loads(record["body"])
            if data.get("forceFail"):
                raise ValueError("Intentional failure for DLQ test")
            if data.get("eventType") != "OrderCreated":
                raise ValueError("Unsupported eventType")
            for name in ("eventId", "orderId"):
                if not isinstance(data.get(name), str) or not data[name]:
                    raise ValueError("Missing " + name)
            item = {"eventId": data["eventId"],
                    "orderId": data["orderId"],
                    "status": "PROCESSED",
                    "createdAt": data.get("createdAt", "test")}
            try:
                table.put_item(Item=item,
                    ConditionExpression="attribute_not_exists(eventId)")
                action = "processed"
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                    raise
                action = "duplicate_skipped"
            print(json.dumps({"action": action,
                              "eventId": data["eventId"]}))
        except Exception as exc:
            print(json.dumps({"action": "failed",
                              "messageId": record["messageId"],
                              "error": str(exc)}))
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}
