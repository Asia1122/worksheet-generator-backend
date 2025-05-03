import os
import json
import boto3
import http.client

# 환경 변수
OPENAI_KEY = os.getenv('OPENAI_API_KEY')
TABLE_NAME = os.getenv('DYNAMODB_TABLE')

# DynamoDB 연결
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)

def call_openai(count, level, topic):
    conn = http.client.HTTPSConnection("api.openai.com")

    # 잘못된 … 문자를 제거하고 실제 텍스트로 교체
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
    content = resp["choices"][0]["message"]["content"]
    return json.loads(content)


def lambda_handler(event, context):
    try:
        body = json.loads(event.get('body','{}'))
        level = body['level']
        topic = body['topic']
        count = int(body.get('count', 10))
        code  = context.aws_request_id[:8]

        # 1) GPT 호출
        qs = call_openai(count, level, topic)

        # 2) DynamoDB에 저장
        with table.batch_writer() as batch:
            for q in qs:
                batch.put_item(Item={
                    'worksheet_code':  code,
                    'question_number': q['number'],
                    'question':        q['stem'],
                    'options':         q['options'],
                    'answerIndex':     q['answerIndex']
                })

        # 3) 응답 반환
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'worksheet_code': code, 'questions': qs})
        }
    except Exception as e:
        print("Error:", str(e))
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }
