import json
import boto3
import os
from datetime import datetime
import uuid

bedrock_agent = boto3.client('bedrock-agent-runtime')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['DYNAMODB_TABLE'])

def lambda_handler(event, context):
    try:
        # Parse input
        body = json.loads(event.get('body', '{}'))
        current_role = body.get('current_role', '')
        goal = body.get('goal', '')
        user_id = body.get('user_id', str(uuid.uuid4()))

        if not current_role or not goal:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'current_role and goal are required'})
            }

        # Create prompt
        prompt = f"""You are an expert career coach. Create a personalized career development plan.

Current Role: {current_role}
Career Goal: {goal}

Provide a comprehensive career development plan that includes:
1. Recommended internal training courses (from the knowledge base)
2. Key skills to develop
3. Suggested timeline (3-6 months)
4. Additional certifications or learning resources

Be specific and actionable."""

        # Call Bedrock Knowledge Base
        kb_id = os.environ.get('KNOWLEDGE_BASE_ID')

        if not kb_id or kb_id == 'UPDATE_AFTER_KB_CREATION':
            return {
                'statusCode': 500,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'error': 'Knowledge Base ID not configured. Please update Lambda environment variable.'
                })
            }

        # Try with retrieval configuration
        response = bedrock_agent.retrieve_and_generate(
            input={'text': prompt},
            retrieveAndGenerateConfiguration={
                'type': 'KNOWLEDGE_BASE',
                'knowledgeBaseConfiguration': {
                    'knowledgeBaseId': kb_id,
                    'modelArn': os.environ['MODEL_ARN'],
                    'generationConfiguration': {
                        'inferenceConfig': {
                            'textInferenceConfig': {
                                'maxTokens': 800
                            }
                        }
                    },
                    'retrievalConfiguration': {
                        'vectorSearchConfiguration': {
                            'numberOfResults': 5
                        }
                    }
                }
            }
        )

        # Extract response
        generated_text = response['output']['text']
        citations = response.get('citations', [])

        # Save to DynamoDB
        timestamp = datetime.utcnow().isoformat()
        table.put_item(Item={
            'user_id': user_id,
            'timestamp': timestamp,
            'current_role': current_role,
            'goal': goal,
            'career_plan': generated_text,
            'citations': citations
        })

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'user_id': user_id,
                'current_role': current_role,
                'goal': goal,
                'career_plan': generated_text,
                'citations': citations,
                'timestamp': timestamp
            }, indent=2)
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }
