from azure.identity import DefaultAzureCredential
from azure.mgmt.subscription import SubscriptionClient
from azure.mgmt.subscription.models import Subscription
from azure.mgmt.resource import ResourceManagementClient


class CachedSubscriptions:
    # We effectively create three indexes of information for quick lookup: subscriptions, resource groups,
    # and resource groups by location.
    subscriptions = {}
    resource_groups = {}
    resource_groups_by_location = {}

    refresh_thread = None

    @staticmethod
    def refresh_all_subscriptions():
        """
        Generates an index of subscriptions, resource groups, and locations.
        :return: None
        """
    
        by_subscription_results = {}
        by_resource_group_results = {}
        by_resource_group_location_results = {}

        # Generate a list of subscriptions using the local credentials
        # IDE note: DefaultAzureCredential() is sometimes highlighted as being an incompatible credential for the
        # SubscriptionClient() credential argument. However, DefaultAzureCredential is of the TokenCredential type
        # and is a valid input for SubscriptionClient (or anywhere else TokenCredential is expected).
        subscriptions = [sub for sub in SubscriptionClient(DefaultAzureCredential()).subscriptions.list()]

        # Iterate over the subscriptions to collect their configurations and resource group information.
        for subscription in subscriptions:
            resource_groups = [
                group.as_dict() for group in
                ResourceManagementClient(credential=DefaultAzureCredential(), subscription_id=subscription.subscription_id).resource_groups.list()
            ]

            # Record the results for this subscription by subscription id.
            by_subscription_results.update(
                {
                    subscription.subscription_id:
                        {
                            'subscription': subscription,
                            'resource_groups':
                                {
                                    group['id']: group
                                    for group in resource_groups
                                }
                        }
                }
            )

            # Record the results for this subscription by resource group identifier.
            by_resource_group_results.update(
                {
                    group['id']:
                        {
                            'group': group,
                            'subscription': subscription,
                        }
                    for group in resource_groups
                }
            )

            # Record resource groups by region (location) code.
            for group in resource_groups:
                gl = group['location']
                if gl not in by_resource_group_location_results.keys():
                    by_resource_group_location_results[gl] = {}

                by_resource_group_location_results[gl][group['id']] = {
                    group['id']: group | {'subscription': subscription}
                }

        # Update the class variables with the collected results.
        CachedSubscriptions.subscriptions = by_subscription_results
        CachedSubscriptions.resource_groups = by_resource_group_results
        CachedSubscriptions.by_group_location_results = by_resource_group_location_results

        from datetime import datetime
        CachedSubscriptions.last_collected = datetime.now()

        if CachedSubscriptions.refresh_thread is None:
            from threading import Thread
            CachedSubscriptions.refresh_thread = Thread(target=CachedSubscriptions.refresh_all_subscriptions, daemon=True)

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
            CachedSubscriptions.refresh_all_subscriptions()
            sleep(600)  # Sleep for 10 minutes before refreshing again
