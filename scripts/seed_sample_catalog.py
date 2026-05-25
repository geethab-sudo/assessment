#!/usr/bin/env python3
"""
Insert sample languages and topics (with related_documents) for local development.
Safe to re-run: skips rows that already exist (by language code and topic name).

Usage (from project root, with DATABASE_URL in .env):
  python scripts/seed_sample_catalog.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
load_dotenv(override=True)

from sqlalchemy import select  # noqa: E402

from services.database import init_db, get_session_factory  # noqa: E402
from services.models import Language, Topic  # noqa: E402

# Sample catalog: general English, Python, Java, Node.js
SAMPLE: list[dict] = [
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
                "related_documents": [
                    {"title": "venv", "url": "https://docs.python.org/3/library/venv.html"},
                    {"title": "PyPA - Installing Packages", "url": "https://packaging.python.org/en/latest/tutorials/installing-packages/"}
                ],
            },
            {
                "name": "Tier 2 - Async (asyncio, async/await)",
                "related_documents": [
                    {"title": "asyncio", "url": "https://docs.python.org/3/library/asyncio.html"},
                    {"title": "RealPython - Async IO", "url": "https://realpython.com/async-io-python/"}
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


def main() -> None:
    init_db()
    sf = get_session_factory()
    created_lang = 0
    created_topic = 0
    skipped_topic = 0
    updated_topic = 0
    deleted_topic = 0
    skipped_lang = 0

    with sf() as session:
        for block in SAMPLE:
            code = block["code"]
            name = block["name"]
            lang = session.scalar(select(Language).where(Language.code == code))
            if not lang:
                lang = Language(code=code, name=name)
                session.add(lang)
                session.flush()
                created_lang += 1
            else:
                skipped_lang += 1

            lid = lang.id

            # Fetch all existing topics for this language in the DB
            db_topics = session.scalars(
                select(Topic).where(Topic.language_id == lid)
            ).all()
            db_topic_map = {t.name: t for t in db_topics}
            seed_topic_names = {t["name"] for t in block["topics"]}

            # 1. For Python, clean up old topics that are no longer in SAMPLE
            if code == "py":
                for db_tname, db_t in db_topic_map.items():
                    if db_tname not in seed_topic_names:
                        session.delete(db_t)
                        deleted_topic += 1

            # 2. Add or update topics
            for t in block["topics"]:
                tname = t["name"]
                docs = t.get("related_documents") or []

                if tname in db_topic_map:
                    # For Python, also update the URLs if they changed
                    if code == "py":
                        db_topic = db_topic_map[tname]
                        if db_topic.related_documents != docs:
                            db_topic.related_documents = docs
                            updated_topic += 1
                        else:
                            skipped_topic += 1
                    else:
                        skipped_topic += 1
                else:
                    session.add(
                        Topic(
                            language_id=lid,
                            name=tname,
                            related_documents=docs,
                        )
                    )
                    created_topic += 1
        session.commit()

    print(
        f"Done. Languages: {created_lang} created, {skipped_lang} already present. "
        f"Topics: {created_topic} created, {updated_topic} updated, {deleted_topic} deleted, {skipped_topic} already present/skipped."
    )


if __name__ == "__main__":
    main()
