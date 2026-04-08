import os
import json
import zulip
import anthropic
import requests
from dotenv import load_dotenv

load_dotenv()

ZAMMAD_URL = os.getenv("ZAMMAD_URL")
ZAMMAD_TOKEN = os.getenv("ZAMMAD_TOKEN")
ZAMMAD_HEADERS = {
	"Authorization": f"Token token={ZAMMAD_TOKEN}",
	"Content-Type": "application/json"
}

ANTHROPIC_CLIENT = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

ZULIP_CLIENT = zulip.Client(config_files="Kanti-zuliprc")

AGENTS = {
        "T1": [
	    {"name": "Helpdesk 1", "email": "helpdesk@homelab.local"},
	    {"name": "Helpdesk 2", "email": "helpdesk2@homelab.local"},
	    {"name": "Helpdesk 3", "email": "helpdesk3@homelab.local"},
	    {"name": "Helpdesk 4", "email": "helpdesk4@homelab.local"},
	],
	"T2": [
	    {"name": "Support 1", "email": "hdsupport1@homelab.local"},
	    {"name": "Support 2", "email": "hdsupport2@homelab.local"},
	    {"name": "Support 3", "email": "hdsupport3@homelab.local"},
	],
	"T3": [
	    {"name": "Engineer 1", "email": "engi1@homelab.local"},
	    {"name": "Engineer 2", "email": "engi2@homelab.local"},
	    {"name": "Engineer 3", "email": "engi3@homelab.local"},
	]
}

roster_position = {
	"T1": 0,
	"T2": 0,
	"T3": 0
}

def get_next_agent(tier):
	agents = AGENTS[tier]
	position = roster_position[tier]
	agent = agents[position]
	roster_position[tier] = (position + 1) % len(agents)
	return agent

def classify_ticket(message):
    with open("prompt.txt", "r") as f:
        prompt_template = f.read()
    
    prompt = prompt_template.replace("{message}", message)
    
    response = ANTHROPIC_CLIENT.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    
    raw_response = response.content[0].text
    raw_response = raw_response.strip()
    if raw_response.startswith("```"):
        raw_response = raw_response.split("```")[1]
        if raw_response.startswith("json"):
            raw_response = raw_response[4:]

    classification = json.loads(raw_response.strip())
    return classification

def get_zammad_user_id(email, full_name=None):
    """Look up a Zammad user ID by email, create customer if not found"""
    response = requests.get(
        f"{ZAMMAD_URL}/api/v1/users/search?query={email}",
        headers=ZAMMAD_HEADERS
    )
    users = response.json()
    
    # User found - return their ID
    if users and len(users) > 0:
        return users[0]["id"]
    
    # User not found - create them as a customer
    print(f"User {email} not found in Zammad, creating customer account...")
    
    # Split full name into first and last
    name_parts = full_name.split(" ") if full_name else ["Unknown", "User"]
    first_name = name_parts[0]
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else "User"
    
    new_user = {
        "firstname": first_name,
        "lastname": last_name,
        "email": email,
        "role_ids": [3],
        "active": True
    }
    
    create_response = requests.post(
        f"{ZAMMAD_URL}/api/v1/users",
        headers=ZAMMAD_HEADERS,
        json=new_user
    )
    
    created_user = create_response.json()
    print(f"Customer created: {created_user.get('email')} with ID: {created_user.get('id')}")
    return created_user.get("id")


def create_zammad_ticket(classification, requester_name, requester_email):
    """Create a ticket in Zammad with the classified information"""

    # Get the assigned agent based on tier
    agent = get_next_agent(classification["tier"])

    # Map tier to Zammad group name
    group_map = {
        "T1": "T1-Helpdesk",
        "T2": "T2-Support",
        "T3": "T3-Engineering"
    }
    group = group_map[classification["tier"]]

    # Look up the agent's Zammad user ID
    agent_id = get_zammad_user_id(agent["email"])

    # Build the ticket payload
    ticket_data = {
        "title": classification["title"],
        "group": group,
        "priority": classification["severity"],
        "state": "new",
        "customer": requester_email,
        "article": {
            "subject": classification["title"],
            "body": f"""
Requester: {requester_name}
Email: {requester_email}

Issue Summary:
{classification["summary"]}

Original Request:
{classification.get("original_message", "")}
            """,
            "type": "note",
            "internal": False
        }
    }

    # Add agent assignment if we found the agent ID
    if agent_id:
        ticket_data["owner_id"] = agent_id

    # Make the API call to create the ticket
    response = requests.post(
        f"{ZAMMAD_URL}/api/v1/tickets",
        headers=ZAMMAD_HEADERS,
        json=ticket_data
    )

    ticket = response.json()

    return {
        "ticket_id": ticket["id"],
        "ticket_number": ticket["number"],
        "agent": agent,
        "group": group,
        "severity": classification["severity"],
        "suggestions": classification["suggestions"]
    }

def send_zulip_message(to_email, subject, message):
    """Send a direct message to a user in Zulip"""
    ZULIP_CLIENT.send_message({
        "type": "direct",
        "to": [to_email],
        "content": message
    })


def notify_requester(requester_email, ticket_result):
    """Send ticket confirmation and AI suggestions to the requester"""

    suggestions_text = "\n".join([
        f"{i+1}. {suggestion}"
        for i, suggestion in enumerate(ticket_result["suggestions"])
    ])

    message = f"""
✅ **Your ticket has been created!**

**Ticket Number:** #{ticket_result["ticket_number"]}
**Severity:** {ticket_result["severity"]}
**Assigned to:** {ticket_result["agent"]["name"]} ({ticket_result["group"]})

**While you wait, here are some things to try:**
{suggestions_text}

A technician will be in touch shortly. If your issue becomes more urgent please create a new ticket.
    """

    send_zulip_message(requester_email, "Ticket Created", message)


def notify_agent(ticket_result, original_message):
    """Send new ticket notification to the assigned agent"""

    message = f"""
🎫 **New ticket assigned to you!**

**Ticket Number:** #{ticket_result["ticket_number"]}
**Severity:** {ticket_result["severity"]}
**Group:** {ticket_result["group"]}

**Issue:**
{original_message}

Please log into Zammad to view and work this ticket.
{ZAMMAD_URL}
    """

    send_zulip_message(ticket_result["agent"]["email"], "New Ticket Assigned", message)

def handle_message(event):
    """Handle incoming Zulip messages and process ticket requests"""

    # Only process messages, ignore other events
    if event["type"] != "message":
        return

    message = event["message"]
    content = message["content"].strip()

    # Only respond to messages starting with !ticket
    if not content.lower().startswith("!ticket"):
        return

    # Extract the actual issue text after !ticket
    issue_text = content[7:].strip()

    # Ignore empty ticket requests
    if not issue_text:
        send_zulip_message(
            message["sender_email"],
            "Invalid Ticket",
            "Please describe your issue after !ticket\nExample: !ticket my computer won't turn on"
        )
        return

    # Let the user know we received their request
    send_zulip_message(
        message["sender_email"],
        "Ticket Request Received",
        "⏳ Processing your request, please wait..."
    )

    try:
        # Step 1 - Classify the ticket with Claude AI
        print(f"Classifying ticket: {issue_text}")
        classification = classify_ticket(issue_text)
        classification["original_message"] = issue_text

        # Step 2 - Create the ticket in Zammad
        print(f"Creating ticket in Zammad - Tier: {classification['tier']}")
        ticket_result = create_zammad_ticket(
            classification,
            message["sender_full_name"],
            message["sender_email"]
        )

        # Step 3 - Notify the requester
        print(f"Notifying requester: {message['sender_email']}")
        notify_requester(message["sender_email"], ticket_result)

        # Step 4 - Notify the assigned agent
        print(f"Notifying agent: {ticket_result['agent']['email']}")
        notify_agent(ticket_result, issue_text)

        print(f"Ticket #{ticket_result['ticket_number']} created successfully")

    except Exception as e:
        print(f"Error processing ticket: {e}")
        send_zulip_message(
            message["sender_email"],
            "Error",
            "Sorry, something went wrong processing your ticket. Please try again or contact helpdesk directly."
        )


def main():
    """Start the bot and listen for messages"""
    print("Helpdesk Bot starting...")
    print(f"Connected to Zulip: {ZULIP_CLIENT.get_profile()['email']}")
    print("Listening for !ticket messages...")

    ZULIP_CLIENT.call_on_each_event(
        handle_message,
        event_types=["message"]
    )


if __name__ == "__main__":
    main()
