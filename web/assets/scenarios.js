// Demo scenarios. Every one of these was validated against the real
// xtrshow.repatch engine before being added here — the reports shown on the
// page are produced by that engine, not transcribed.

export const SCENARIOS = {
  basic: {
    label: "Basic",
    desc: "Two hunks with @ annotations. The annotations show up in the apply report, so a failure tells the model what it was trying to do.",
    file: "server.py",
    seed: {
      "server.py":
`import time


def connect(host):
    return Socket(host)


def fetch(url):
    resp = get(url)
    return resp.body
`,
    },
    patch:
`--- a/server.py
@ Add a connect timeout
<<<<
def connect(host):
    return Socket(host)
====
def connect(host, timeout=30):
    return Socket(host, timeout=timeout)
>>>>

@ Raise on non-200 responses
<<<<
    resp = get(url)
    return resp.body
====
    resp = get(url)
    resp.raise_for_status()
    return resp.body
>>>>
`,
  },

  whitespace: {
    label: "Fuzzy whitespace",
    desc: "The search block has the wrong indentation — a mistake models make constantly. Matching is whitespace-insensitive, so it still lands.",
    file: "config.py",
    seed: {
      "config.py":
`class Config:
    def __init__(self):
        self.retries = 3
        self.debug = False
`,
    },
    patch:
`--- a/config.py
@ Model lost the indentation, applies anyway
<<<<
self.retries = 3
====
        self.retries = 5
>>>>
`,
  },

  wildcard: {
    label: "Wildcard anchors",
    desc: "~~~~ skips volatile interior lines. The model anchors on the signature and the return statement without having to reproduce the middle exactly.",
    file: "handler.py",
    seed: {
      "handler.py":
`def process(payload):
    log.info("start")
    data = parse(payload)
    validate(data)
    transform(data)
    enrich(data)
    return commit(data)
`,
    },
    patch:
`--- a/handler.py
@ Anchor on signature + return, skip the middle
<<<<
def process(payload):
~~~~
    return commit(data)
====
def process(payload, dry_run=False):
    log.info("start")
    data = parse(payload)
    validate(data)
    transform(data)
    enrich(data)
    if dry_run:
        return data
    return commit(data)
>>>>
`,
  },

  tail: {
    label: "Hint + tail context",
    desc: "User.save and Order.save are byte-identical. The line hint (<<<< 7) picks which one; the tail context after the second ==== proves the hunk landed where it meant to.",
    file: "models.py",
    seed: {
      "models.py":
`class User:
    def save(self):
        db.write(self)


class Order:
    def save(self):
        db.write(self)


class Invoice:
    pass
`,
    },
    patch:
`--- a/models.py
@ Audit only Order.save, not User.save
<<<< 7
    def save(self):
        db.write(self)
====
    def save(self):
        audit(self)
        db.write(self)
====


class Invoice:
>>>>
`,
  },

  insert: {
    label: "Insert / create",
    desc: "An empty search block with a line hint is a pure insertion. An empty search block with no hint on a path that does not exist creates the file.",
    file: "app.py",
    seed: {
      "app.py":
`import os
import sys


def main():
    run()
`,
    },
    patch:
`--- a/app.py
@ Pure insertion at line 3
<<<< 3
====
from logging import getLogger
>>>>

--- a/logger.py
@ Brand new file
<<<<
====
from logging import getLogger

log = getLogger(__name__)
>>>>
`,
  },

  delete: {
    label: "Delete",
    desc: "A real search block with an empty replace deletes a section. ! DELETE FILE removes a whole file — backed up first, like everything else.",
    file: "utils.py",
    seed: {
      "utils.py":
`def helper():
    return 1


def deprecated_thing():
    warn("do not use")
    return None


def other():
    return 2
`,
      "legacy.py": `old_flag = True\n`,
    },
    patch:
`--- a/utils.py
@ Drop the dead function
<<<<
def deprecated_thing():
    warn("do not use")
    return None
====
>>>>

--- a/legacy.py
@ Remove the whole file
! DELETE FILE
`,
  },

  failure: {
    label: "Failure",
    desc: "The first hunk is hallucinated — no such code exists. It fails, the second still applies, and a .rpterr bundle is written that you can paste straight back to the model.",
    file: "auth.py",
    seed: {
      "auth.py":
`def login(user, pw):
    return check(user, pw)


def logout(user):
    session.drop(user)
`,
    },
    patch:
`--- a/auth.py
@ Hallucinated - no such code in the file
<<<<
def login(user, pw, mfa):
    return check_mfa(user, pw, mfa)
====
def login(user, pw, mfa=None):
    return check(user, pw)
>>>>

@ This one is fine
<<<<
def logout(user):
    session.drop(user)
====
def logout(user):
    audit("logout", user)
    session.drop(user)
>>>>
`,
  },
};
