# Agents

Each file here is one team member: their **role**, **allocated skills**,
**responsibilities**, the **interface they own**, links to their detailed plan, and a
running **working-notes log**. These are AI agent personas used to organize the work —
in reality one owner (+ AI) builds this; treat the personas as workstreams, not headcount.

```
                 Abdo  (Project Manager)
                   │
                 Kian  (Technical Expert / Architect)
                   │
 ┌────────┬────────┬────────┬────────┬────────┬────────┐
Zoriaz   Vivek    Omar     Nour     Iona     Matt    Solove
Frontend  API   Pre-proc  OCR    Translate Glossary  Store
```

## Leadership
- [Abdo — Project Manager](abdo.md)
- [Kian — Technical Expert / Architect](kian.md)

## Component specialists
- [Zoriaz — Web Frontend](zoriaz.md)
- [Vivek — API / Backend & Orchestration](vivek.md)
- [Omar — Pre-processor](omar.md)
- [Nour — OCR Adapter](nour.md)
- [Iona — Translator](iona.md)
- [Matt — Glossary Store](matt.md)
- [Solove — Result Store](solove.md)

## How notes work
Append to the **Working notes & log** section in each file as work progresses
(newest at the bottom, dated). The authoritative cross-component contract everyone
follows is [`../docs/team/CONTRACT.md`](../docs/team/CONTRACT.md) (code:
[`../tests/contracts/contracts.py`](../tests/contracts/contracts.py)).
