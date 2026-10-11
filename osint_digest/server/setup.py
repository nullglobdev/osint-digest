"""Plain terminal menus for container setup, settings, models, and sources."""
from copy import deepcopy
import getpass
import warnings

from osint_digest.core.collector import error_label
from osint_digest.core.providers import PROVIDERS, KEY_ENV, list_models
from osint_digest.core.sources import make_source
from osint_digest.core import scopes
from osint_digest.server.settings import (BusyError, SettingsError, load_config, save_config, require_ready,
                                         validate_webhooks)


def prompt(title, default=''):
    answer = input(title + (f' [{default}]' if default != '' else '') + ': ').strip()
    return answer or str(default)


def secret(title, current=''):
    hint = 'saved; Enter to keep, - to clear' if current else 'hidden input; Enter to leave empty'
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        try:
            answer = getpass.getpass(f'{title} ({hint}): ').strip()
        except getpass.GetPassWarning:
            raise SettingsError('Cannot hide terminal input. Reconnect with a terminal that supports hidden passwords.') from None
    return '' if answer == '-' else answer or current


def yes(title, default=False):
    while True:
        answer = prompt(title + (' (Y/n)' if default else ' (y/N)')).lower()
        if not answer:
            return default
        if answer in ('y', 'yes', 'n', 'no'):
            return answer in ('y', 'yes')
        print('Enter y or n.')


def number(title, default, minimum, maximum):
    while True:
        try:
            value = int(prompt(title, default))
            if minimum <= value <= maximum:
                return value
        except ValueError:
            pass
        print(f'Enter a whole number from {minimum} to {maximum}.')


def choose_model(config):
    provider = config['provider']
    if provider == 'none':
        print('Publisher excerpts do not need a model.')
        return
    profile = config['profiles'].setdefault(provider, {'api_key': '', 'model': '', 'allow_paid': False})
    models = []
    if (provider == 'ollama' or profile.get('api_key')) and yes('Load available models from this provider now?', True):
        try:
            models = list_models(provider, profile.get('api_key', ''), config['ollama_url'])
        except Exception as error:
            print('Model discovery failed: ' + error_label(error) + '. You can enter a model ID below.')
    page = 0
    while models:
        print('\nAvailable models (listing does not guarantee generation support or quota):')
        for index in range(page * 20, min((page + 1) * 20, len(models))):
            print(f'{index + 1}. {models[index]}')
        choice = prompt('Number, n/p for next/previous page, or Enter to type/keep a model ID')
        if not choice:
            break
        if choice.lower() in ('n', 'p'):
            page = (page + (1 if choice.lower() == 'n' else -1)) % ((len(models) + 19) // 20)
        elif choice.isdigit() and 1 <= int(choice) <= len(models):
            profile['model'] = models[int(choice) - 1]
            return
        else:
            print('Choose a listed number or press Enter.')
    profile['model'] = prompt('Model ID', profile.get('model', '')).removeprefix('models/') if provider == 'gemini' else prompt('Model ID', profile.get('model', ''))


def webhooks_menu(config):
    targets = config['webhooks']
    while True:
        print('\nDiscord webhooks (every enabled destination receives the same articles):')
        for index, target in enumerate(targets, 1):
            print(f"{index}. {'ON ' if target['enabled'] else 'OFF'} {target['name']} | URL saved")
        print('a Add | e Edit name/URL | t Enable/disable | r Remove | 0 Done')
        action = prompt('Action', '0').lower()
        try:
            if action == '0':
                return
            if action == 'a':
                target = {'name': prompt('Destination name (for example, Security team)'),
                          'url': secret('Discord webhook URL'), 'enabled': True}
                validate_webhooks([*targets, target])
                targets.append(target)
            elif action in ('e', 't', 'r'):
                if not targets:
                    print('Add a webhook first.')
                    continue
                index = number('Webhook number', 1, 1, len(targets)) - 1
                target = targets[index]
                if action == 't':
                    target['enabled'] = not target['enabled']
                elif action == 'e':
                    edited = {**target, 'name': prompt('Destination name', target['name']),
                              'url': secret('Discord webhook URL', target['url'])}
                    validate_webhooks(targets[:index] + [edited] + targets[index + 1:])
                    targets[index] = edited
                elif yes('Remove this webhook? Its delivery history will be retained.'):
                    targets.pop(index)
            else:
                print('Choose one of the displayed actions.')
        except SettingsError as error:
            print(str(error))


def connection(config):
    choices = list(PROVIDERS.items())
    print('\nSummary providers:')
    for index, (title, _) in enumerate(choices, 1):
        print(f'{index}. {title}')
    current = next(i for i, (_, value) in enumerate(choices, 1) if value == config['provider'])
    config['provider'] = choices[number('Provider', current, 1, len(choices)) - 1][1]
    provider = config['provider']
    if provider == 'none':
        return
    profile = config['profiles'].setdefault(provider, {'api_key': '', 'model': '', 'allow_paid': False})
    if provider in KEY_ENV:
        profile['api_key'] = secret('AI API key for ' + provider, profile.get('api_key', ''))
        print('Cloud AI uses your own provider account and quota.')
    if provider in ('openai', 'anthropic'):
        profile['allow_paid'] = yes('Enable usage-billed AI calls for this provider?', profile.get('allow_paid', False))
    if provider == 'ollama':
        print('Use an Ollama endpoint reachable from the container, such as http://ollama:11434.')
        config['ollama_url'] = prompt('Ollama base URL', config['ollama_url'])
    choose_model(config)


def schedule(config):
    config['per_source_limit'] = number('Articles per source per check', config['per_source_limit'], 1, 100)
    config['interval_minutes'] = number('Check every (minutes)', config['interval_minutes'], 15, 360)
    print('Every enabled source is checked. Only articles published in the last 48 hours qualify, newest first. Previously delivered articles are skipped. The per-source limit includes retries.')
    config['enabled'] = yes('Enable automatic checks?', config['enabled'])


def scope_menu(config):
    keys = list(scopes.LABELS)
    while True:
        selected = scopes.selection(config)
        print('\nArticle filters: all selected scopes must match before AI analysis. All means no restriction.')
        for index, key in enumerate(keys, 1):
            print(f'{index}. {scopes.LABELS[key]}: {scopes.CHOICES[key][selected[key]]}')
        print('8 Reset all filters | 0 Done')
        action = number('Change scope', 0, 0, 8)
        if action == 0:
            return
        if action == 8:
            config.update(scopes.DEFAULTS)
            continue
        key = keys[action - 1]
        choices = list(scopes.CHOICES[key])
        for index, value in enumerate(choices):
            print(f'{index}. {scopes.CHOICES[key][value]}')
        option = number(scopes.LABELS[key], choices.index(selected[key]), 0, len(choices) - 1)
        config[key] = choices[option]
        print('Keywords: ' + scopes.keywords(key, config[key]))
        print('OR means alternatives; + requires both concepts in the article. Only matching articles count toward the per-source limit.')


def sources_menu(config):
    sources = config['sources']
    while True:
        print('\nSources (every enabled source is checked; order sets test sampling priority):')
        for index, source in enumerate(sources, 1):
            print(f"{index}. {'ON ' if source.get('enabled', True) else 'OFF'} {source['name']} | {source['feed']}")
        print('a Add | e Edit | t Enable/disable | m Move | r Remove | 0 Done')
        action = prompt('Action', '0').lower()
        if action == '0':
            return
        try:
            if action == 'a':
                sources.append(make_source(prompt('Publisher name'), prompt('HTTPS RSS/Atom feed URL'),
                    prompt('Additional allowed article/redirect hosts (comma separated)'), sources))
            elif action in ('e', 't', 'm', 'r'):
                if not sources:
                    print('Add a source first.')
                    continue
                index = number('Source number', 1, 1, len(sources)) - 1
                source = sources[index]
                if action == 't':
                    source['enabled'] = not source.get('enabled', True)
                elif action == 'e':
                    print('Publisher name stays fixed to retain delivery history: ' + source['name'])
                    sources[index] = make_source(source['name'], prompt('Feed URL', source['feed']),
                        prompt('Allowed article/redirect hosts', ','.join(source['hosts'])), sources,
                        editing=index, enabled=source.get('enabled', True))
                elif action == 'm':
                    target = number('New position', index + 1, 1, len(sources)) - 1
                    sources.insert(target, sources.pop(index))
                elif yes('Remove this source? Delivery history will be retained.'):
                    sources.pop(index)
            else:
                print('Choose one of the displayed actions.')
        except ValueError as error:
            print(str(error))


def edit(root, section):
    config, revision = load_config(root)
    config = deepcopy(config)
    if section == 'setup':
        print('\nOSINT Digest server setup\nCredentials are hidden while typing and saved in a private file in the data volume.')
        webhooks_menu(config)
        connection(config)
        schedule(config)
        scope_menu(config)
        if yes('Review or add publisher sources now?'):
            sources_menu(config)
    else:
        {'connection': connection, 'schedule': schedule, 'sources': sources_menu,
         'models': choose_model, 'webhooks': webhooks_menu, 'scope': scope_menu, 'filters': scope_menu}[section](config)
    if config['enabled']:
        require_ready(config)
    save_config(root, config, revision)
    print('Saved. The running service picks up changes; an active task finishes with its original settings.')


def administer(root, command):
    if command != 'settings':
        edit(root, command)
        return
    from osint_digest.server.app import run_action, show_status, backup
    while True:
        print('\nOSINT Digest settings\n1 AI connection\n2 Schedule and articles per source\n3 Sources\n4 Models\n5 Show status\n6 Check feeds\n7 Test AI (local preview)\n8 Preview eligible unsent articles\n9 Test mode (limited articles; repeats allowed)\n10 Check all sources and send eligible unsent articles\n11 Check all enabled Discord connections (no message)\n12 Back up settings and history\n13 Webhooks\n14 Article filters\n0 Exit')
        choice = prompt('Choice', '0')
        try:
            if choice == '0':
                return
            if choice in ('1', '2', '3', '4', '13', '14'):
                edit(root, {'1': 'connection', '2': 'schedule', '3': 'sources', '4': 'models', '13': 'webhooks', '14': 'scope'}[choice])
            elif choice == '5':
                show_status(root)
            elif choice == '12':
                backup(root)
            elif choice == '9':
                print('Test mode applies to this task only. Choose a timeframe up to 365 days; articles must still be available in publisher feeds. Automatic checks keep the 48-hour window and skip delivered articles.')
                config, _ = load_config(root)
                count = number('Articles per source for this test', config['per_source_limit'], 1, 100)
                days = number('Test article timeframe (days)', 2, 1, 365)
                task = prompt('1 Preview locally | 2 Send to all enabled webhooks | 0 Cancel', '1')
                if task in ('1', '2'):
                    code = run_action(root, 'preview' if task == '1' else 'new', count=count, test_mode=True, test_days=days)
                    print(f'Test finished (exit code {code}).')
            elif choice in ('6', '7', '8', '10', '11'):
                action = {'6': 'check-feeds', '7': 'test-ai', '8': 'preview', '10': 'new', '11': 'test-discord'}[choice]
                options = {'test_days': number('Test article timeframe (days)', 2, 1, 365)} if action in ('test-ai', 'preview') else {}
                code = run_action(root, action, **options)
                print(f'Command finished (exit code {code}).')
            else:
                print('Choose one of the displayed numbers.')
        except (SettingsError, BusyError) as error:
            print(str(error))
        except Exception as error:
            print('Operation failed: ' + error_label(error))
