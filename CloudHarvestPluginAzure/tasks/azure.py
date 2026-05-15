from CloudHarvestCoreTasks.dataset import WalkableDict
from CloudHarvestCoreTasks.tasks import BaseTask
from CloudHarvestCorePluginManager.decorators import register_definition


@register_definition(name='azure', category='task')
class AzureTask(BaseTask):

    def __init__(self,
                 command: str,
                 arguments: dict = None,
                 client_arguments: dict = None,
                 service: str = None,
                 type: str = None,
                 account: str = None,
                 region: str = None,
                 paginator_method: str = 'as_dict',
                 include_metadata: bool = True,
                 global_service: bool = False,
                 max_retries: int = 10,
                 result_path: str or list or tuple = None,
                 *args,
                 **kwargs):
        """
        Constructs all the necessary attributes for the AzureTask object.

        Args:
            command (str): The package and command path to execute for the service.
            arguments (dict): The arguments to pass to the final command. Defaults to empty dictionary.
            client_arguments (dict, optional): Arguments to pass to the command's client class.
            service (str, optional): The Azure service to interact with (e.g., 's3', 'ec2'). If not specified, the default is pulled from the task chain variables.
            type (str, optional): The type of the Azure service (e.g., 's3', 'ec2'). If not specified, the default is pulled from the task chain variables.
            account (str, optional): The Azure number to use for the session. If not specified, the default is pulled from the task chain variables.
            region (str, optional): The Azure region to use for the session. None is supported as not all Azure services require a region. If not specified, the default is pulled from the task chain variables.
            paginator_method (str, optional): The method to use to paginate results. Default is 'as_dict'.
            include_metadata (bool, optional): When True, some 'Harvest' metadata fields are added to the result. Defaults to True.
            global_service (bool, optional): If True, the service is considered a global service (e.g., IAM). Negates the 'region' input. Defaults to False.
            max_retries (int, optional): The maximum number of retries for the command. Defaults to 10.
            result_path (str, optional): Path to the results. When not provided, the path is the response itself.
        """

        # Initialize parent class
        super().__init__(*args, **kwargs)

        # Set STAR: Service, Type, Account, Region, (Resource) Group
        self.service = service or self.task_chain.variables.get('service')
        self.type = type or self.task_chain.variables.get('type')
        self.account = str(account or self.task_chain.variables.get('account'))     # Azure "subscription_id"
        self.region = None if global_service else region or self.task_chain.variables.get('region')     # Azure "location"
        self.group = None  # Azure resource_group
        self.paginator_method = paginator_method or 'as_dict'

        # azure sdk configuration
        self.command = command
        self.arguments = arguments or {}
        self.client_arguments = client_arguments or {}
        self.max_retries = max_retries

        # Output manipulation
        self.include_metadata = include_metadata
        self.result_path = result_path

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
            subscription=self.account,
            command=self.command,
            arguments=self.arguments,
            client_arguments=self.client_arguments,
            max_retries=self.max_retries,
            result_path=self.result_path,
            paginator_method=self.paginator_method
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
        subscription: str,
        command: str,
        arguments: dict,
        client_arguments: dict,
        paginator_method: str,
        max_retries: int,
        result_path
) -> WalkableDict:
    """
    Queries Azure for the specified service and command.

    Arguments
        subscription (str): The Azure subscription_id to query.
        command (str): The command to execute on the Azure service.
        arguments (dict): The arguments to pass to the command.
        client_arguments (dict): The arguments to pass to the command's client class.
        paginator_method (str): The method to use to paginate results. Default is 'as_dict'.
        credentials (dict, optional): The Azure credentials to use for the session.
        max_retries (int, optional): The maximum number of retries for the command. Defaults to 10.
        result_path (str, optional): Path to the results. When not provided, the path is the object itself.

    Returns:
        Any: The result of the Azure query.
    """
    max_retries = max_retries or 10

    # Initialize the result and attempt counter
    attempt = 0

    # Verify that the `command` is formatted correctly
    from re import match
    if not match(r"^[a-zA-Z0-9._-]+:[a-zA-Z0-9._-]+$", command):
        raise ValueError('azure `command` must be in the format "package:ClientClass.method1.method2.methodn" (e.g., "azure.mgmt.postgresqlflexibleservers:PostgreSQLManagementClient.servers.list_by_resource_group") format.')

    # `command` is a loaded argument. It requires the following syntax: 'package:ClassName.path.to.method' where
    # `arguments` will be fed to the final method in the path. This is required because many Azure commands are nested
    # such as: `azure.mgmt.postgresqlflexibleservers:PostgreSQLManagementClient().servers.list_by_resource_group()`.
    command_package, command_class = command.split(':')
    command_methods = command_package.split('.')[1:]

    # Dynamically import the Azure client's module
    try:
        from importlib import import_module
        azure_module = import_module(command_package)

    except ModuleNotFoundError as e:
        raise ModuleNotFoundError(f'`{command_package}` could not be loaded.') from e

    # Check that the client class exists
    if not hasattr(azure_module, command_class):
        raise Exception(f'`{command_package}`.{command_class} does not exist.')

    # The client object allows connection to the Azure API.
    from CloudHarvestPluginAzure.credentials import CachedSubscriptions
    # Add the credentials to the client arguments, overriding 'credentials' if provided
    client_arguments.update({'credentials': CachedSubscriptions.get_subscription(subscription)})

    # Instantiate the client object with the provided arguments.
    client = getattr(azure_module, command_class)(**client_arguments)

    # Set and verify the client's method chain using functools.reduce which walks the entire class_methods chain and
    # returns the last method in sequence.
    try:
        from functools import reduce
        command_method = reduce(getattr, command_methods, client)

    except Exception as e:
        raise Exception(f'Could not find a method in {command_package}:{command_class}.{".".join(command_methods)}.') from e

    # Initialize the result dictionary.
    result = {}

    # Start a loop to execute the command
    while True:
        # Increment the attempt counter
        attempt += 1

        try:
            # If the maximum number of retries is exceeded, raise an exception
            if attempt > max_retries:
                raise Exception('Max retries exceeded')

            # Execute the command. Unlike boto3, Azure SDK documentation claims that pagination is handled automatically
            # by the client, so we don't need to check for pagination here; however, the automated pagination is managed
            # through the act of iterating over the response. Therefore, we encapsulate the getattr() operation in a
            # list comprehension with the expectations that a valid response will paginate.
            # https://learn.microsoft.com/en-us/azure/developer/python/sdk/fundamentals/common-types-response

            # The paginator_method is sometimes required to convert the Azure responses into useful data. For example,
            # the PostgreSQLManagementClient().servers.list_by_resource_group() method returns a class that requires
            # the as_dict() method to derive responses in JSON.
            if paginator_method:
                result = [
                    getattr(r, paginator_method)() for r in command_method(**arguments)
                ]

            else:
                result = [
                    r for r in command_method(**arguments)
                ]

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

    result = WalkableDict(result)

    # If a result key is specified, extract the result using the key. If no result key was specified, then return
    # the object as-is (no-op)
    if isinstance(result_path, str):
        result = result.walk(result_path)

    elif isinstance(result_path, (list, tuple)):
        result = {
            path: result.walk(path)
            for path in result_path
        }

    return result if isinstance(result, WalkableDict) and result is not None else WalkableDict(result)
