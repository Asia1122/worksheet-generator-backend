import os
import json
import boto3
import http.client

OPENAI_KEY = os.getenv('OPENAI_API_KEY')
DYNAMODB_TABLE = os.getenv('DYNAMODB_TABLE')

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(DYNAMODB_TABLE)

def call_openai(count, level, topic):
    conn = http.client.HTTPSConnection("api.openai.com")

    prompt = (
        f"Generate {count} multiple-choice questions for {level}학년 "
        f"on the topic '{topic}'. "
        "Return a JSON array of objects with keys: number, stem, options (list), answerIndex."
    )
    payload = json.dumps({
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": "You are a helpful teacher."},
            {"role": "user",   "content": prompt}
        ],
        "temperature": 0.7
    })
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {OPENAI_KEY}'
    }

    conn.request("POST", "/v1/chat/completions", payload, headers)
    res = conn.getresponse()
    body = res.read().decode()

    if res.status != 200:
        print(f"OpenAI API error {res.status}: {body}")
        raise Exception(f"OpenAI API responded {res.status}")

    resp = json.loads(body)
    raw = resp["choices"][0]["message"]["content"]

    # 응답에서 JSON 배열 부분만 추출
    start = raw.find('[')
    end   = raw.rfind(']')
    if start == -1 or end == -1:
        print("JSON parsing error, content:", raw)
        raise Exception("Could not find JSON array in response")
    json_str = raw[start:end+1]

    return json.loads(json_str)

def lambda_handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))
        level = body['level']
        topic = body['topic']
        count = int(body.get('count', 10))
        code  = context.aws_request_id[:8]

        questions = call_openai(count, level, topic)

        with table.batch_writer() as batch:
            for q in questions:
                batch.put_item(Item={
                    'worksheet_code':  code,
                    'question_number': q['number'],
                    'question':        q['stem'],
                    'options':         q['options'],
                    'answerIndex':     q['answerIndex']
                })

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'worksheet_code': code, 'questions': questions})
        }

    except Exception as e:
        print("Error:", str(e))
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }
