from typing import Any, Dict, AsyncGenerator, Optional

import aioboto3


class AsyncDynamoDBClient:

    def __init__(self, table_name):
        self.table_name = table_name

    async def put_item(self, item):
        session = aioboto3.Session()
        async with session.resource('dynamodb') as dynamodb:
            table = await dynamodb.Table(self.table_name)
            await table.put_item(
                Item=item
            )

    async def query(
        self,
        key_condition_expression: str,
        expression_attribute_values: Dict[str, Any],
        index_name: Optional[str] = None,
        filter_expression: Optional[str] = None,
        limit: Optional[int] = None,
        scan_index_forward: bool = True,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        session = aioboto3.Session()
        async with session.resource('dynamodb') as dynamodb:
            table = await dynamodb.Table(self.table_name)
            exclusive_start_key = {}
            while True:
                query_args = {
                    "KeyConditionExpression": key_condition_expression,
                    "ExpressionAttributeValues": expression_attribute_values,
                    "ScanIndexForward": scan_index_forward,
                }
                # Only add ExclusiveStartKey if it's not empty
                if exclusive_start_key:
                    query_args["ExclusiveStartKey"] = exclusive_start_key
                if index_name:
                    query_args["IndexName"] = index_name
                if filter_expression:
                    query_args["FilterExpression"] = filter_expression
                if limit:
                    query_args["Limit"] = limit

                response = await table.query(**query_args)
                for item in response.get("Items", []):
                    yield item

                exclusive_start_key = response.get("LastEvaluatedKey", {})
                if not exclusive_start_key:
                    break

    async def scan(
            self,
            projection_expression: Optional[str],
            filter_expression: Optional[str] = None,
            expression_attribute_values: Optional[Dict[str, Any]] = None,
            limit: Optional[int] = None,
            index_name: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        session = aioboto3.Session()
        async with session.resource('dynamodb') as dynamodb:
            table = await dynamodb.Table(self.table_name)
            exclusive_start_key = {}
            while True:
                scan_args = {}
                if projection_expression:
                    scan_args["ProjectionExpression"] = projection_expression
                if filter_expression:
                    scan_args["FilterExpression"] = filter_expression
                if expression_attribute_values:
                    scan_args["ExpressionAttributeValues"] = expression_attribute_values
                if limit:
                    scan_args["Limit"] = limit
                if index_name:
                    scan_args["IndexName"] = index_name
                if exclusive_start_key:
                    scan_args["ExclusiveStartKey"] = exclusive_start_key

                response = await table.scan(**scan_args)
                for item in response.get("Items", []):
                    yield item

                exclusive_start_key = response.get("LastEvaluatedKey", {})
                if not exclusive_start_key:
                    break
