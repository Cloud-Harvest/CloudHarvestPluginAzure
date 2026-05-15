from CloudHarvestCoreTasks.dataset import WalkableDict
from CloudHarvestCoreTasks.tasks import BaseTask
from CloudHarvestCorePluginManager.decorators import register_definition
from azure.mgmt.resourcegraph.models import QueryRequest


@register_definition(name='azure', category='task')
class AzureTask(BaseTask):

    def __init__(self,
                 service: str = None,
                 type: str = None,
                 account: str = None,
                 region: str = None,
                 include_metadata: bool = True,
                 # global_service: bool = False,
                 max_retries: int = 10,
                 result_path: str or list or tuple = None,
                 *args,
                 **kwargs):
        """
        Constructs all the necessary attributes for the AzureTask object.

        Args:
            service (str, optional): The Azure service to interact with (e.g., 's3', 'ec2'). If not specified, the default is pulled from the task chain variables.
            type (str, optional): The type of the Azure service (e.g., 's3', 'ec2'). If not specified, the default is pulled from the task chain variables.
            account (str, optional): The Azure number to use for the session. If not specified, the default is pulled from the task chain variables.
            region (str, optional): The Azure region to use for the session. None is supported as not all Azure services require a region. If not specified, the default is pulled from the task chain variables.
            include_metadata (bool, optional): When True, some 'Harvest' metadata fields are added to the result. Defaults to True.
            max_retries (int, optional): The maximum number of retries for the command. Defaults to 10.
        """

        # Initialize parent class
        super().__init__(*args, **kwargs)

        # Set STAR: Service, Type, Account (Subscription), Region (Resource) Group
        self.service = service or self.task_chain.variables.get('service')
        self.type = type or self.task_chain.variables.get('type')
        self.account = str(account or self.task_chain.variables.get('account'))     # Azure "subscription_id"
        self.region = region or self.task_chain.variables.get('region')     # Azure "location"

        # azure sdk configuration
        self.max_retries = max_retries

        # Output manipulation
        self.include_metadata = include_metadata
        self.result_path = result_path or 'data'

        # Programmatic attributes
        self.account_alias = None

        # Initialize parent class again
        super().__init__(*args, **kwargs)

    def method(self):
        """
        Executes the command on the Azure service and stores the result.

        Raises:
            Exception: If the maximum number of retries is exceeded or no result is returned from the command.

        Returns:
            self: Returns the instance of the AzureTask.
        """
        from CloudHarvestPluginAzure.credentials import CachedSubscriptions
        subscription  = CachedSubscriptions.subscriptions.get(self.account)

        # Set the account_alias attribute
        if subscription:
            self.account_alias = subscription['subscription'].name

        # Execute the Azure query
        result = query_azure(
            service=self.service,
            service_type=self.type,
            account=self.account,
            region=self.region,
            max_retries=self.max_retries,
        )

        # Add starting metadata to the result
        if self.include_metadata:
            if isinstance(result, list):
                for record in result:
                    if isinstance(record, dict):
                        record['Harvest'] = {
                            'AccountId': self.account,
                            'AccountName': self.account_alias
                        }

            elif isinstance(result, dict):
                result['Harvest'] = {
                    'AccountId': self.account,
                    'AccountName': self.account_alias
                }

        # Store the result
        self.result = result

        # Return the instance of the AzureTask
        return self


def query_azure(
        service: str,
        service_type: str,
        account: str,
        region: str,
        max_retries: int,
) -> list:
    """
    Queries Azure for the specified service and command.

    Arguments
        service (str): The Azure subscription_id to query.
        service_type (str): The Azure resource type to query.
        account (str): The Azure subscription_id to query.
        region (str): The Azure location to query
        credentials (dict, optional): The Azure credentials to use for the session.
        max_retries (int, optional): The maximum number of retries for the command. Defaults to 10.
        result_path (str, optional): Path to the results. When not provided, the path is the object itself.

    Returns:
        Any: The result of the Azure query.
    """
    from azure.identity import DefaultAzureCredential
    from azure.mgmt.resourcegraph import ResourceGraphClient
    from azure.mgmt.resourcegraph.models import QueryRequest, QueryRequestOptions, QueryResponse
    max_retries = max_retries or 10

    # Initialize the result and attempt counter
    attempt = 0

    # Initialize the result dictionary.
    result = []
    client = ResourceGraphClient(DefaultAzureCredential())

    # Start a loop to execute the command
    while True:
        # Increment the attempt counter
        attempt += 1

        try:
            # If the maximum number of retries is exceeded, raise an exception
            if attempt > max_retries:
                raise Exception('Max retries exceeded')

            # Pagination loop
            skip_token = None
            while True:
                # Build the query
                query = QueryRequest(
                    query=f"resources | where"
                          f" type == 'microsoft.{service}/{service_type}'"
                          f" location == '{region}'"
                          f" subscriptionId == '{account}'",
                    options=QueryRequestOptions(
                        skip_token=skip_token,
                    )
                )

                pagination_result = client.resources(query).as_dict()
                result.append(pagination_result.get('data'))

                if pagination_result.get('skip_token'):
                    skip_token = pagination_result.get('skip_token')

                else:
                    break

            # If no errors occurred during processing, we can assume that (even an empty) result is a success.
            break

        # Retry throttling or request errors, but raise others
        except Exception as e:
            # If the error is due to throttling, sleep for a while and then retry
            if any(error_code in '-'.join(e.args) for error_code in ('Throttling', 'TooManyRequestsException')):
                from time import sleep
                sleep(2 * attempt)

            # If the error is due to any other reason, raise it
            else:
                raise e from e

    # Determine the 'data' type of all responses. We expect that 'data' is always a list of dictionaries.
    result_types = list(set(type(r) for r in result))
    if len(result_types) == 1:
        if result_types[0] == list:
            result = [
                item
                for sublist in result
                for item in sublist
            ]

        elif result_types[0] == dict:
            result = {
                key: value
                for r in result
                for key, value in r.items()
            }
            # Convert the result to a list because that's what the calling method expects
            result = [result]
    else:
        raise Exception(f'Inconsistent result type: {result_types}')

    return result
