"""Plain terminal menus for container setup, settings, models, and sources."""
from copy import deepcopy
import getpass
import warnings

from osint_digest.core.collector import error_label
from osint_digest.core.providers import PROVIDERS, KEY_ENV, list_models
from osint_digest.core.sources import make_source
from osint_digest.server.settings import (BusyError, SettingsError, load_config, save_config, require_ready)


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


def connection(config):
    config['webhook'] = secret('Discord webhook URL', config['webhook'])
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
    config['max_posts'] = number('Articles per run', config['max_posts'], 1, 20)
    config['interval_minutes'] = number('Check every (minutes)', config['interval_minutes'], 15, 360)
    print('Automatic checks send new articles and retries. The first successful check creates a quiet baseline.')
    config['enabled'] = yes('Enable automatic checks?', config['enabled'])


def sources_menu(config):
    sources = config['sources']
    while True:
        print('\nSources (order determines which publishers a latest batch uses):')
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
        connection(config)
        schedule(config)
        if yes('Review or add publisher sources now?'):
            sources_menu(config)
    else:
        {'connection': connection, 'schedule': schedule, 'sources': sources_menu, 'models': choose_model}[section](config)
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
        print('\nOSINT Digest settings\n1 Connection and AI\n2 Schedule and article limit\n3 Sources\n4 Models\n5 Show status\n6 Check feeds\n7 Test AI (local preview)\n8 Preview latest batch\n9 Send latest batch to Discord (can repeat posts)\n10 Check and send new\n11 Check Discord connection (no message)\n12 Back up settings and history\n0 Exit')
        choice = prompt('Choice', '0')
        try:
            if choice == '0':
                return
            if choice in ('1', '2', '3', '4'):
                edit(root, {'1': 'connection', '2': 'schedule', '3': 'sources', '4': 'models'}[choice])
            elif choice == '5':
                show_status(root)
            elif choice == '12':
                backup(root)
            elif choice in ('6', '7', '8', '9', '10', '11'):
                action = {'6': 'check-feeds', '7': 'test-ai', '8': 'preview', '9': 'batch', '10': 'new', '11': 'test-discord'}[choice]
                if action == 'batch' and not yes('Send this latest batch now, including articles previously sent?'):
                    continue
                code = run_action(root, action)
                print(f'Command finished (exit code {code}).')
            else:
                print('Choose one of the displayed numbers.')
        except (SettingsError, BusyError) as error:
            print(str(error))
        except Exception as error:
            print('Operation failed: ' + error_label(error))
