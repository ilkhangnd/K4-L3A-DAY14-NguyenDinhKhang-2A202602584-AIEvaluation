# OrbitTech Support Lab UI

This static UI renders saved OrbitTech benchmark artifacts. It does not call
OpenAI and does not read .env.

From the repository root, start a local server with:

    python3 -m http.server 8000

Then open http://localhost:8000/demo_ui/ in a browser.

Use the suggested questions or search a saved benchmark question. The inspector
shows the five metrics, Overall score, failure label, and ordered retrieved
evidence for the selected case.
