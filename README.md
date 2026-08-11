# Projects-Pros

Monorepo of standalone AI/agent projects. Each subdirectory is self-contained — its own dependencies, README, and deployment config.

| Project | Description | Stack |
| --- | --- | --- |
| [MultiAgentClinicalTrial-IntelligenceusingLangGraphLangMemGCP](MultiAgentClinicalTrial-IntelligenceusingLangGraphLangMemGCP/) | MOSAIC — multi-agent clinical trial intelligence | LangGraph, LangMem, GCP |
| [TripMateAI](TripMateAI/) | Travel planning assistant with flight, train, and web-search tools | Flask, Docker, Tavily |

## Working in this repo

Each project owns its virtualenv and requirements:

```bash
cd <project>
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

The root `.gitignore` carries the shared Python/tooling rules; projects add their own for data, credentials, and framework-specific state.

## License

[MIT](LICENSE)
