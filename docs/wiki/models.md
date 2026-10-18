# Models and AI

[Wiki home](README.md) | [Examples](examples.md) | [Troubleshooting](troubleshooting.md)

Choose **Publisher excerpts** to work without AI. Supported AI providers are Google Gemini, OpenAI, Anthropic Claude, and a separately running Ollama service. Use model discovery or enter a model ID available to your account; availability is provider-dependent.

```sh
sh scripts/server.sh settings
sh scripts/server.sh models
sh scripts/server.sh test-ai
```

Configure the provider/key in Settings, then choose a model. Keys and models are saved separately per provider. OpenAI/Claude require explicit usage-billing opt-in. `test-ai` summarizes one eligible article and saves a preview without Discord delivery; it still uses quota. Filters and the normal 48-hour window apply unless a test timeframe is supplied.

On Windows use **Connection**, choose the provider, key and model, then **Save connection**. Dev mode exposes AI tests. Windows credentials use account encryption and cannot be migrated to Linux by copying the profile.

## Ollama

Ollama and its models are separate from Digest. Inside Docker, `127.0.0.1` means the Digest container. The supplied Compose file maps `host.docker.internal` to the host gateway; `http://host.docker.internal:11434` requires Ollama to listen on an interface reachable from the container. A same-network service can use its Docker service name. Limit access to intended clients.

Discovery and generation use the configured endpoint; cloud keys are not sent to Ollama. See [networking guidance](../CONTAINER.md#ollama-connectivity).

Review generated claims against the article. Changing a model does not regenerate cached server reports awaiting delivery.

Implementation: [providers](../../osint_digest/core/providers.py), [settings](../../osint_digest/server/settings.py). Evidence: [server tests](../../tests/test_server.py).
