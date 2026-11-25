import os
import json
import boto3
import requests
import re
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.exceptions import NoCredentialsError
from flask import Flask, render_template, request

# Initialize the Flask application
app = Flask(__name__)

# The API endpoint URL
API_URL = os.environ.get("API_URL", "").strip()

def request_career_plan(payload):
    """Sign the server-side API call with the configured AWS profile/role."""
    session = boto3.Session()
    if not session.region_name:
        raise ValueError("Set AWS_DEFAULT_REGION to the API Gateway region.")
    credentials = session.get_credentials()
    if credentials is None:
        raise NoCredentialsError()

    body = json.dumps(payload).encode("utf-8")
    signed_request = AWSRequest(
        method="POST",
        url=API_URL,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    SigV4Auth(
        credentials.get_frozen_credentials(), "execute-api", session.region_name
    ).add_auth(signed_request)
    return requests.post(
        API_URL,
        data=body,
        headers=dict(signed_request.headers),
        timeout=35,
        allow_redirects=False,
    )

def format_career_plan(plan_text):
    """
    Parses the raw string from the API into a structured dictionary
    that's easier to render in the HTML template.
    """
    if not plan_text:
        return None

    # Use a more robust regex to find sections starting with a number and a period.
    # This splits the text into sections like "1. ...", "2. ...", etc.
    sections_raw = re.split(r'\n(?=\d\.\s)', plan_text)
    
    plan = {
        'title': '',
        'sections': [],
        'note': ''
    }

    # The first part is the intro text before the numbered sections
    intro_parts = sections_raw[0].split('\n\n', 1)
    plan['title'] = intro_parts[0].strip()
    
    if len(intro_parts) > 1:
        first_section_text = intro_parts[1]
    else: # Handle cases where there might not be a newline after the title
        first_section_text = ''
        
    # The first section might not have been captured by the split if it's part of the first element
    if first_section_text:
        sections_raw[0] = first_section_text

    # Process each section
    for section_text in sections_raw:
        lines = [line.strip() for line in section_text.strip().split('\n') if line.strip()]
        if not lines:
            continue
            
        heading = lines[0]
        items = [item.lstrip('- ').strip() for item in lines[1:]]
        
        # Check if the last item is the "Note"
        final_note = ''
        if items and items[-1].lower().startswith('note:'):
            final_note = items.pop().lstrip('Note:').strip()
            plan['note'] = final_note

        # --- FIX IS HERE ---
        # Renamed the key from 'items' to 'section_items' to avoid conflict
        # with the built-in dictionary .items() method in Jinja2.
        plan['sections'].append({'heading': heading, 'section_items': items})

    return plan


@app.route('/', methods=['GET', 'POST'])
def index():
    """
    Main route to handle the form submission and display the career plan.
    """
    career_plan = None
    error_message = None

    if request.method == 'POST':
        current_role = request.form.get('current_role')
        goal = request.form.get('goal')

        if not current_role or not goal:
            error_message = "Both 'Current Role' and 'Career Goal' are required."
        elif not API_URL:
            error_message = "API_URL is not configured. Set it to the CloudFormation ApiEndpoint output and restart the app."
        else:
            payload = {
                "current_role": current_role,
                "goal": goal
            }
            try:
                response = request_career_plan(payload)
                print(f"API Response Status Code: {response.status_code}")
                response.raise_for_status()

                api_data = response.json()

                raw_plan = api_data.get("career_plan")
                
                if raw_plan:
                    career_plan = format_career_plan(raw_plan)
                else:
                    error_message = "API returned a valid response, but no career plan was found."

            except requests.exceptions.RequestException as e:
                # Handle network errors, timeouts, etc.
                error_message = f"An error occurred while contacting the API: {e}"
                print(f"ERROR: {error_message}")
            except Exception as e:
                # Handle other potential errors (e.g., JSON parsing)
                error_message = f"An unexpected error occurred: {e}"
                print(f"ERROR: {error_message}")


    return render_template('index.html', career_plan=career_plan, error_message=error_message)

# To run the app, execute `python app.py` in your terminal
if __name__ == '__main__':
    # Ensure the 'templates' folder exists before running
    if not os.path.exists('templates'):
        os.makedirs('templates')
        print("Created 'templates' directory. Please place 'index.html' inside it.")
    
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=5001)

