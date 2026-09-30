# OrbitTech Support Lab UI

This UI supports both modes:

- **Find case** searches the 20 saved benchmark cases and shows their scores.
- **Send** calls the local RAG endpoint, which retrieves corpus chunks and asks
  the existing DomainAssistant for a new answer.

The server reads OPENAI_API_KEY only from .env. The browser never receives the
key, golden expected answers, or gold evaluation contexts.

From the repository root, start a local server with:

    python3 demo_ui/server.py --port 8001

Then open http://localhost:8001/demo_ui/ in a browser. You may omit --port
when port 8000 is available.

Use the suggested questions or **Find case** for a saved benchmark question.
Use **Send** for a new question. Live chats show retrieved evidence but do not
show benchmark metrics because they have no prepared expected answer.
