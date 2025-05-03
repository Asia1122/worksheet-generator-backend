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
    prompt = ( … )
    payload = json.dumps({ … })
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {OPENAI_KEY}'
    }
    conn.request("POST", "/v1/chat/completions", payload, headers)

    # 응답 받기
    res = conn.getresponse()
    body = res.read().decode()

    # ← 여기부터 상태 체크
    if res.status != 200:
        # 상태 코드가 200이 아니면 에러 로그를 찍고 예외 발생
        print(f"OpenAI API error {res.status}: {body}")
        raise Exception(f"OpenAI API responded {res.status}")
    # ← 상태 체크 끝

    # 정상 응답인 경우 JSON 파싱
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
