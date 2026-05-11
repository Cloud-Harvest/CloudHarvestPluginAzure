from CloudHarvestCoreTasks.exceptions import BaseHarvestException


class HarvestAzureException(BaseHarvestException):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class HarvestAzureDataCollectionException(BaseHarvestException):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class HarvestAzureTaskException(BaseHarvestException):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
