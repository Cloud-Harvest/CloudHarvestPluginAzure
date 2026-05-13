from azure.identity import DefaultAzureCredential
from azure.mgmt.subscription import SubscriptionClient
from azure.mgmt.subscription.models import Subscription
from azure.mgmt.resource import ResourceManagementClient


class CachedSubscriptions:
    subscriptions = {}
    refresh_thread = None

    @staticmethod
    def get_all_subscriptions() -> dict:
        # Generates an index of Azure subscriptions by id and their associated resource groups.
        results = {}

        # Generate a list of subscriptions using the local credentials
        # IDE note: DefaultAzureCredential() is sometimes highlighted as being an incompatible credential for the
        # SubscriptionClient() credential argument. However, DefaultAzureCredential is of the TokenCredential type
        # and is a valid input for SubscriptionClient (or anywhere else TokenCredential is expected).
        subscriptions = [sub for sub in SubscriptionClient(DefaultAzureCredential()).subscriptions.list()]

        # Iterate over the subscriptions to collect their configurations and resource group information.
        for subscription in subscriptions:
            resource_groups = [
                group for group in
                ResourceManagementClient(subscription.credential, subscription.subscription_id).resource_groups.list()
            ]

            results.update(
                {
                    subscription.subscription_id: {
                        "subscription": subscription,
                        "resource_groups": {
                            group.name: group
                            for group in resource_groups
                        },
                    }
                }
            )

        CachedSubscriptions.subscriptions = results
        from datetime import datetime
        CachedSubscriptions.last_collected = datetime.now()

        if CachedSubscriptions.refresh_thread is None:
            from threading import Thread
            CachedSubscriptions.refresh_thread = Thread(target=CachedSubscriptions.get_all_subscriptions, daemon=True)

        return results

    @staticmethod
    def get_subscription(subscription_id: str) -> Subscription | None:
        """
        Safely returns a Subscription object if it exists.
        :param subscription_id: The subscription ID to look up.
        :return: Subscription object or None.
        """
        if CachedSubscriptions.subscriptions.get(subscription_id):
            return CachedSubscriptions.subscriptions[subscription_id]['subscription']

        else:
            return None

    @staticmethod
    def _refresh_thread():
        from time import sleep

        while True:
            CachedSubscriptions.get_all_subscriptions()
            sleep(600)  # Sleep for 10 minutes before refreshing again
