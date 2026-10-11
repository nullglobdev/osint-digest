"""Fan out one report with durable, independent receipts and retries per webhook."""
import time

from osint_digest.core import collector as bot
from osint_digest.server.settings import active_webhooks, atomic_json, webhook_id


class WebhookDelivery:
    def __init__(self, config):
        self.targets = [(webhook_id(t['url']), t) for t in active_webhooks(config)]
        self.legacy_id = config.get('legacy_webhook_id', '')

    def complete(self, receipts):
        return bool(self.targets) and all(receipts.get(identity, {}).get('status') == 'sent'
                                         for identity, _ in self.targets)

    def prepare(self, state):
        if 'deliveries' not in state:
            state['deliveries'] = {}
            if self.legacy_id:
                for url, receipt in state['seen'].items():
                    if receipt.get('status') == 'sent':
                        state['deliveries'][url] = {self.legacy_id: dict(receipt)}
        if not self.targets:
            return  # A preview with no destination can still review articles.
        identities = sorted(identity for identity, _ in self.targets)
        if state.get('delivery_targets') != identities:
            # New/re-enabled destinations need currently available articles even
            # if the publisher's feed has not changed since the last request.
            for feed in state['feeds'].values():
                feed['delivery_only'] = False
            state['delivery_targets'] = identities
        for url in set(state['seen']) | set(state['deliveries']):
            receipts = state['deliveries'].get(url, {})
            if self.complete(receipts):
                state['seen'][url] = dict(receipts[self.targets[0][0]])
            else:
                state['seen'].pop(url, None)

    def is_due(self, entry, state):
        if not self.targets:
            return True
        receipts = state['deliveries'].get(entry['url'], {})
        return any(receipts.get(identity, {}).get('status') != 'sent'
                   and receipts.get(identity, {}).get('retry_after', 0) <= time.time()
                   for identity, _ in self.targets)

    def send(self, entry, report, state, path, *, test_mode, stop_requested, max_age_hours=None):
        receipts = state['deliveries'].setdefault(entry['url'], {})
        failures = 0
        if not test_mode:
            # Reuse the exact report after a partial delivery or restart. This
            # avoids another publisher fetch and AI call for a webhook retry.
            entry['delivery_report'] = report
            state['pending'][entry['url']] = entry
        for identity, target in self.targets:
            if stop_requested():
                break
            if not bot.within_window(entry, max_age_hours):
                print('Article aged out of the publication window; remaining webhooks skipped.', flush=True)
                break
            previous = receipts.get(identity, {})
            if not test_mode and (previous.get('status') == 'sent' or previous.get('retry_after', 0) > time.time()):
                continue
            try:
                message_id = bot.send_discord(report, webhook=target['url'])
            except Exception as error:
                failures += 1
                if not test_mode:
                    attempts = previous.get('attempts', 0) + 1
                    receipts[identity] = {'status': 'failed', 'attempts': attempts,
                        'retry_after': time.time() + min(86400, 1800 * 2 ** min(attempts, 5)),
                        'last_error': type(error).__name__}
                print(f"WARNING Discord [{target['name']}]: {bot.error_label(error)}; "
                      + ('test failed; normal retry unchanged' if test_mode else 'retained for retry'), flush=True)
            else:
                receipts[identity] = {'status': 'sent', 'at': bot.now(), 'message_id': message_id}
                print(f"DELIVERED Discord [{target['name']}]", flush=True)
            # Checkpoint before the next destination, including on graceful stop.
            # Storage failures propagate; continuing could lose acknowledged posts.
            atomic_json(path, state)
        complete = self.complete(receipts)
        receipt = receipts[self.targets[0][0]].get('message_id') if complete else None
        return receipt, complete, failures
