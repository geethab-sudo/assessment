"""Default catalog languages and topics (Tier 1 presets + sample languages)."""

from __future__ import annotations

from typing import Any

SAMPLE_CATALOG: list[dict] = [
    {
        "code": "en",
        "name": "English (general CS)",
        "topics": [
            {
                "name": "Programming fundamentals (variables, types, control flow)",
                "related_documents": [
                    {
                        "title": "Structure and semantics of programs",
                        "url": "https://en.wikipedia.org/wiki/Computer_programming",
                    },
                ],
            },
            {
                "name": "Data structures and algorithms",
                "related_documents": [
                    {
                        "title": "Big O overview",
                        "url": "https://en.wikipedia.org/wiki/Big_O_notation",
                    },
                ],
            },
            {
                "name": "Databases and SQL",
                "related_documents": [
                    {
                        "title": "SQL tutorial",
                        "url": "https://www.w3schools.com/sql/",
                    },
                ],
            },
            {
                "name": "REST APIs and HTTP",
                "related_documents": [
                    {
                        "title": "MDN — HTTP overview",
                        "url": "https://developer.mozilla.org/en-US/docs/Web/HTTP/Overview",
                    },
                ],
            },
        ],
    },
    {
        "code": "py",
        "name": "Python",
        "topics": [
            {
                "name": "Tier 1 - Data Structures & Manipulation (Lists, Sets, Strings)",
                "related_documents": [
                    {"title": "Python Data Structures", "url": "https://docs.python.org/3/tutorial/datastructures.html"},
                    {"title": "RealPython - Data Structures", "url": "https://realpython.com/python-data-structures/"}
                ],
            },
            {
                "name": "Tier 1 - Logic & Flow Control (Conditionals, Loops, Comprehensions)",
                "related_documents": [
                    {"title": "Python Control Flow", "url": "https://docs.python.org/3/tutorial/controlflow.html"},
                    {"title": "RealPython - List Comprehensions", "url": "https://realpython.com/list-comprehension-python/"}
                ],
            },
            {
                "name": "Tier 1 - OOP Basics (Classes, Methods, Encapsulation)",
                "related_documents": [
                    {"title": "Python Classes", "url": "https://docs.python.org/3/tutorial/classes.html"},
                    {"title": "RealPython - OOP", "url": "https://realpython.com/python3-object-oriented-programming/"}
                ],
            },
            {
                "name": "Tier 1 - Functions & Dictionaries (Nested lookups, signatures, defaults)",
                "related_documents": [
                    {"title": "Python Functions", "url": "https://docs.python.org/3/tutorial/controlflow.html#defining-functions"},
                    {"title": "Mutable Default Arguments Gotcha", "url": "https://docs.python-guide.org/writing/gotchas/#mutable-default-arguments"}
                ],
            },
            {
                "name": "Tier 1 - Error Handling (Basic try-except, raising exceptions)",
                "related_documents": [
                    {"title": "Python Errors and Exceptions", "url": "https://docs.python.org/3/tutorial/errors.html"},
                    {"title": "RealPython - Exceptions", "url": "https://realpython.com/python-exceptions/"}
                ],
            },
            {
                "name": "Tier 1 - Type Hinting & Annotations (Typing module, static analysis support)",
                "related_documents": [
                    {"title": "Python Typing", "url": "https://docs.python.org/3/library/typing.html"},
                    {"title": "Mypy Cheat Sheet", "url": "https://mypy.readthedocs.io/en/stable/cheat_sheet_py3.html"}
                ],
            },
            {
                "name": "Tier 1 - Built-in Iterators & Utilities (enumerate, zip, any, all)",
                "related_documents": [
                    {"title": "Python Built-in Functions", "url": "https://docs.python.org/3/library/functions.html"},
                    {"title": "RealPython - Enumerate", "url": "https://realpython.com/python-enumerate/"}
                ],
            },
            {
                "name": "Tier 1 - Basic File I/O & Context Managers (with open statements)",
                "related_documents": [
                    {"title": "Python Reading and Writing Files", "url": "https://docs.python.org/3/tutorial/inputoutput.html#reading-and-writing-files"},
                    {"title": "RealPython - With Statement", "url": "https://realpython.com/python-with-statement/"}
                ],
            },
            {
                "name": "Tier 1 - Modules, Namespaces & Imports (Absolute/Relative, Circular imports)",
                "related_documents": [
                    {"title": "Python Modules", "url": "https://docs.python.org/3/tutorial/modules.html"},
                    {"title": "RealPython - Imports", "url": "https://realpython.com/absolute-vs-relative-python-imports/"}
                ],
            },
            {
                "name": "Tier 1 - Generators & Iterables (yield, generator expressions)",
                "related_documents": [
                    {"title": "Python Generators", "url": "https://docs.python.org/3/tutorial/classes.html#generators"},
                    {"title": "RealPython - Generators", "url": "https://realpython.com/introduction-to-python-generators/"}
                ],
            },
            {
                "name": "Tier 1 - Testing (unittest, pytest)",
                "related_documents": [
                    {"title": "unittest", "url": "https://docs.python.org/3/library/unittest.html"},
                    {"title": "pytest - Getting Started", "url": "https://docs.pytest.org/en/stable/getting-started.html#get-started"},
                    {"title": "pytest - How-To Guides", "url": "https://docs.pytest.org/en/stable/how-to/index.html#how-to"},
                    {"title": "pytest - Explanation", "url": "https://docs.pytest.org/en/stable/explanation/index.html#explanation"}
                ],
            },
            {
                "name": "Tier 1 - Packaging and virtual environments (venv)",
                "coding_editor_language": "shell",
                "related_documents": [
                    {"title": "venv", "url": "https://docs.python.org/3/library/venv.html"},
                    {"title": "PyPA - Installing Packages", "url": "https://packaging.python.org/en/latest/tutorials/installing-packages/"}
                ],
            },
            {
                "name": "Tier 2 - Resilience & Reliability: Retry decorators, exponential backoff, jitter.",
                "modality": "pyodide",
                "related_documents": [
                    {"title": "AWS Architecture: Exponential Backoff and Jitter", "url": "https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/"},
                    {"title": "Python functools", "url": "https://docs.python.org/3/library/functools.html#functools.wraps"}
                ],
            },
            {
                "name": "Tier 2 - Security: PII/Credit card Regex redaction strings, AuthN vs AuthZ boundaries.",
                "modality": "pyodide",
                "related_documents": [
                    {"title": "OWASP Python Security Cheat Sheet", "url": "https://cheatsheetseries.owasp.org/cheatsheets/Python_Security_Cheat_Sheet.html"},
                    {"title": "Python Regular Expressions", "url": "https://docs.python.org/3/library/re.html"}
                ],
            },
            {
                "name": "Tier 2 - LLM Output Validation & Repair: String manipulation for parsing and validating broken JSON.",
                "modality": "pyodide",
                "related_documents": [
                    {"title": "Python JSON Processing", "url": "https://docs.python.org/3/library/json.html"},
                    {"title": "Anthropic Prompt Engineering", "url": "https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview"}
                ],
            },
            {
                "name": "Tier 2 - Observability: Dictionary manipulation for injecting Trace/Correlation IDs, span propagation.",
                "modality": "pyodide",
                "related_documents": [
                    {"title": "Python Logging HOWTO", "url": "https://docs.python.org/3/howto/logging.html"},
                    {"title": "OpenTelemetry Context Propagation", "url": "https://opentelemetry.io/docs/languages/python/"}
                ],
            },
            {
                "name": "Tier 2 - Performance: Python Data Model logic like __slots__ memory footprint restrictions.",
                "modality": "pyodide",
                "related_documents": [
                    {"title": "Python Data Model __slots__", "url": "https://docs.python.org/3/reference/datamodel.html#slots"}
                ],
            },
            {
                "name": "Tier 2 - LLM Integration: Live API calls to the Google Gemini API (model configuration, prompting, text generation).",
                "modality": "jupyter",
                "related_documents": [
                    {"title": "Gemini API Python Quickstart", "url": "https://ai.google.dev/gemini-api/docs/quickstart?lang=python"},
                    {"title": "Gemini API Key Setup and Configuration", "url": "https://ai.google.dev/gemini-api/docs/api-key"}
                ],
            },
            {
                "name": "Tier 2 - Data & Persistence Patterns: Real SQLAlchemy sessions, demonstrating database transactions, connection pooling, cache-aside, and the \"Lost Update\" anomaly.",
                "modality": "jupyter",
                "related_documents": [
                    {"title": "Python Contextlib", "url": "https://docs.python.org/3/library/contextlib.html"},
                    {"title": "RealPython Context Managers", "url": "https://realpython.com/python-with-statement/"}
                ],
            },
            {
                "name": "Tier 2 - Real Async Concurrency: Hitting live HTTP endpoints concurrently using httpx.AsyncClient or similar tools and measuring true non-blocking event loops vs synchronous blockages.",
                "modality": "jupyter",
                "related_documents": [
                    {"title": "Python Asyncio Basics", "url": "https://docs.python.org/3/library/asyncio.html"},
                    {"title": "RealPython Async Features", "url": "https://realpython.com/python-async-features/"}
                ],
            },
        ],
    },
    {
        "code": "java",
        "name": "Java",
        "topics": [
            {
                "name": "Java platform and syntax (JDK, JRE, first programs)",
                "related_documents": [
                    {
                        "title": "Java Tutorials — Getting Started",
                        "url": "https://dev.java/learn/",
                    },
                ],
            },
            {
                "name": "Java OOP (classes, interfaces, inheritance, polymorphism)",
                "related_documents": [
                    {
                        "title": "Classes and Objects",
                        "url": "https://docs.oracle.com/javase/tutorial/java/concepts/",
                    },
                ],
            },
            {
                "name": "Java collections and generics",
                "related_documents": [
                    {
                        "title": "Collections trail",
                        "url": "https://docs.oracle.com/javase/tutorial/collections/index.html",
                    },
                ],
            },
            {
                "name": "Java exceptions and try-with-resources",
                "related_documents": [
                    {
                        "title": "Exceptions",
                        "url": "https://docs.oracle.com/javase/tutorial/essential/exceptions/index.html",
                    },
                ],
            },
            {
                "name": "JVM, memory, and garbage collection (basics)",
                "related_documents": [
                    {
                        "title": "Memory management",
                        "url": "https://docs.oracle.com/javase/specs/jvms/se8/html/jvms-2.html#jvms-2.5.4",
                    },
                ],
            },
            {
                "name": "Java concurrency (threads, Executors, basics)",
                "related_documents": [
                    {
                        "title": "Concurrency",
                        "url": "https://docs.oracle.com/javase/tutorial/essential/concurrency/index.html",
                    },
                ],
            },
        ],
    },
    {
        "code": "node",
        "name": "Node.js",
        "topics": [
            {
                "name": "Node.js and JavaScript fundamentals (runtime, REPL, modules)",
                "related_documents": [
                    {
                        "title": "Node.js — Getting started",
                        "url": "https://nodejs.org/en/learn/getting-started/introduction-to-nodejs",
                    },
                ],
            },
            {
                "name": "npm, package.json, and the module system (CommonJS / ESM)",
                "related_documents": [
                    {
                        "title": "Node.js modules",
                        "url": "https://nodejs.org/api/modules.html",
                    },
                ],
            },
            {
                "name": "Asynchronous JavaScript (callbacks, Promises, async/await)",
                "related_documents": [
                    {
                        "title": "Event loop and async",
                        "url": "https://developer.mozilla.org/en-US/docs/Learn/JavaScript/Asynchronous",
                    },
                ],
            },
            {
                "name": "Node built-ins (fs, path, http, streams)",
                "related_documents": [
                    {
                        "title": "File system",
                        "url": "https://nodejs.org/api/fs.html",
                    },
                ],
            },
            {
                "name": "Web APIs with Node (Express or Fastify style routing)",
                "related_documents": [
                    {
                        "title": "Express — Getting started",
                        "url": "https://expressjs.com/en/starter/installing.html",
                    },
                ],
            },
            {
                "name": "Testing in Node (test runner, Jest, or Mocha — concepts)",
                "related_documents": [
                    {
                        "title": "Node test runner",
                        "url": "https://nodejs.org/api/test.html",
                    },
                ],
            },
        ],
    },
]
