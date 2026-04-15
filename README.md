# Zbotproject — AI-Powered Helpdesk Ticketing Bot

An AI-powered helpdesk ticketing pipeline that integrates Zulip, 
Zammad, and Claude AI for automated ticket creation, classification, 
and agent routing.

## What it does
- Listens for `!ticket` commands in Zulip channels
- Uses Claude AI to classify severity and determine the correct support tier
- Automatically creates tickets in Zammad with proper priority and assignment
- Routes tickets to T1/T2/T3 agents via round-robin assignment
- Sends confirmation and AI-generated troubleshooting suggestions to the requester
- Notifies assigned agents via Zulip DM

## Architecture
- **Zulip** — chat platform and ticket intake
- **Zammad** — ticketing system backend
- **Claude AI (Haiku)** — ticket classification and suggestion generation
- **Python** — bot logic and API integration

## Stack
- Python 3.12
- zulip library
- anthropic library
- requests library
- python-dotenv

## Setup
1. Clone the repo
2. Copy `.env.example` to `.env` and fill in your credentials
3. Add your `zuliprc` file
4. Install dependencies: `pip install -r requirements.txt`
5. Run: `python3 bot.py`

## Configuration
See `.env.example` for required environment variables.

## License
MIT License — see LICENSE file for details.

## Author
Charles Messinger — built as a homelab learning project