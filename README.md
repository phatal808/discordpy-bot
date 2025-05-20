---
title: Discord Reaction/FAQ bot
description: A Discord bot written in Python
tags:
  - python
  - discord.py
---

# Discord.py Example

This example starts a Discord bot using [discord.py](https://discordpy.readthedocs.io/en/stable/).

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template/PxM3nl)

## ✨ Features

- Python
- Discord.py

## 💁‍♀️ How to use

- Install packages using `pip install -r requirements.txt`
- Start the bot using `python mm.py`
- Admin always has access create phrases however a role will be needed for anyone else

## Usage ##

-   /trigger

-   subtriggers:
-   /addtrigger
-   Example usage: /addtrigger phrase:"hello there" action:reaction emoji:"👋"
-   Example usage: /addtrigger phrase:"gm" action:reply response:"Good morning ☀️"
-   
-   /listtriggers
-   /removetrigger

## 📝 Notes ##

-  supports external emojis
-  supports animated emojis
