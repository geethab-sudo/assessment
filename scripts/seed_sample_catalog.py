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
                "name": "Python basics (syntax, types, control flow)",
                "related_documents": [
                    {
                        "title": "The Python Tutorial",
                        "url": "https://docs.python.org/3/tutorial/index.html",
                    },
                ],
            },
            {
                "name": "Python functions and modules",
                "related_documents": [
                    {
                        "title": "Functions",
                        "url": "https://docs.python.org/3/tutorial/controlflow.html#defining-functions",
                    },
                ],
            },
            {
                "name": "Python OOP (classes, inheritance)",
                "related_documents": [
                    {
                        "title": "Classes",
                        "url": "https://docs.python.org/3/tutorial/classes.html",
                    },
                ],
            },
            {
                "name": "Python data structures (list, dict, set, tuple)",
                "related_documents": [
                    {
                        "title": "Data structures",
                        "url": "https://docs.python.org/3/tutorial/datastructures.html",
                    },
                ],
            },
            {
                "name": "Python error handling and exceptions",
                "related_documents": [
                    {
                        "title": "Errors and exceptions",
                        "url": "https://docs.python.org/3/tutorial/errors.html",
                    },
                ],
            },
            {
                "name": "Python testing (unittest, pytest)",
                "related_documents": [
                    {
                        "title": "unittest",
                        "url": "https://docs.python.org/3/library/unittest.html",
                    },
                ],
            },
            {
                "name": "Python async (asyncio, async/await)",
                "related_documents": [
                    {
                        "title": "asyncio",
                        "url": "https://docs.python.org/3/library/asyncio.html",
                    },
                ],
            },
            {
                "name": "Python packaging and virtual environments",
                "related_documents": [
                    {
                        "title": "venv",
                        "url": "https://docs.python.org/3/library/venv.html",
                    },
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
    skipped_lang = 0
    skipped_topic = 0

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
            for t in block["topics"]:
                tname = t["name"]
                docs = t.get("related_documents") or []
                existing = session.scalar(
                    select(Topic).where(
                        Topic.language_id == lid,
                        Topic.name == tname,
                    )
                )
                if existing:
                    skipped_topic += 1
                    continue
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
        f"Topics: {created_topic} created, {skipped_topic} already present."
    )


if __name__ == "__main__":
    main()
