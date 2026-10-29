# Background

The longer introduction of the former README, moved unchanged: what Apothicaire is and is not, who builds it, and how it fits with Caladrius and OptChat.

## In plain words

**What this is.** Apothicaire is a pharmacokinetics assistant that runs entirely on one consumer PC: a single graphics card with 12 GB, nothing sent to the cloud. You give it a table of drug concentrations over time and ask questions in French or English: what is the half-life, the clearance, how do two ways of computing the area under the curve differ. It does not calculate. A language model (Bonsai 2 27B, a "ternary" model from PrismML) reads the request, calls the Caladrius engine, and explains what the engine returned. Around the model are three parts that are not AI: the Caladrius engine, which produces every number; a deterministic check, `gate.py`, which flags any number in an answer that is not found in a tool result or in the user's own message; and a benchmark, in `bench/`, which measures how often the whole thing fails.

**What this is not.** It is a prototype and an experiment. It is not a product and not a replacement for anything. It must never be used for a real patient or for a regulatory decision. The numbers in [benchmark.md](benchmark.md) come from synthetic exercises simulated by Caladrius, not from patients. They are also thin: one run of each benchmark, one sampling, one model, scripted questions, and a scoring script whose labels I adjusted after reading the first results (the section "Benchmark" of [benchmark.md](benchmark.md) lists each change). They are counts, not guarantees.

**Who is building it, and why.** I am Abdallah (abdou-rgd on GitHub). I hold a Master's degree in health data science (Université Paris-Saclay), I am in the Master's programme in pharmacokinetic modelling at Université Paris Cité, and I was a pharmacometrics intern at Sanofi R&D. I want to do a PhD at the meeting point of drug metabolism and pharmacokinetics (DMPK) and artificial intelligence. This repository is where I test the question that motivates that goal: can a small local AI be trusted with pharmacokinetic numbers? The longer story of the author is in the Caladrius README.

**How it fits with Caladrius.** Caladrius is the other half of the project: a calculation engine in Rust whose every output is checked against an independent calculation. Apothicaire reaches it through the Model Context Protocol (MCP), as a list of tools: import a table, run a non-compartmental analysis, read a result, export a table, compare two analyses. The model sees seven tools in all. For the full picture of the system, with a diagram, read the section "In plain words" of the [Caladrius README](https://github.com/abdou-rgd/caladrius) and open `docs/explainer.html` in that repository.

**Why OptChat.** A long conversation does not fit in the context of a 12 GB card. OptChat is an idea by Victor Taelin: keep the whole chat on disk and show the model a view in which recent messages are verbatim and older ones are merged into summary lines, arranged as a tree. Nothing is deleted. My prototype of it is published at <https://github.com/abdou-rgd/optchat> (MIT OR Apache-2.0), cloned as the sibling folder `../optchat/`, and Apothicaire imports it unchanged.

## Model licences

- the model weights and inference builds the scripts download or call, each under its own terms. The Liquid AI `d1` models (LFM Open License v1.0, which limits commercial use to organisations under 10 M$ of annual revenue) appear only in the zero-shot baseline of the decision spike (`decision/zero_shot_d1.py`), not in the assistant.
