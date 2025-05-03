import os
import json
import boto3
import openai

# 환경 변수에서 설정값 가져오기
TABLE_NAME      = os.getenv('DYNAMODB_TABLE')
REGION          = os.getenv('AWS_REGION')
openai.api_key  = os.getenv('OPENAI_API_KEY')

# DynamoDB 테이블 객체
dynamodb = boto3.resource('dynamodb', region_name=REGION)
table    = dynamodb.Table(TABLE_NAME)

def lambda_handler(event, context):
    # 요청 바디 파싱
    body  = json.loads(event['body'])
    level = body['level']                   # 예: "3"
    topic = body['topic']                   # 예: "세자리 수의 덧셈"
    count = int(body.get('count', 10))      # 문항 수
    # 워크시트 고유 코드 (context.aws_request_id 앞 8글자)
    code  = body.get('worksheet_code', '') or context.aws_request_id[:8]

    # GPT 호출 프롬프트 구성
    prompt = (
        f"Generate {count} multiple-choice questions for {level}학년 "
        f"on the topic '{topic}'. "
        "Return a JSON array of objects with keys: number, stem, options (list), answerIndex."
    )
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful teacher."},
            {"role": "user",   "content": prompt}
        ],
        temperature=0.7,
    )
    mcqs = json.loads(response.choices[0].message.content)

    # DynamoDB에 일괄 저장
    with table.batch_writer() as batch:
        for q in mcqs:
            batch.put_item(Item={
                'worksheet_code':  code,
                'question_number': q['number'],
                'question':        q['stem'],
                'options':         q['options'],
                'answerIndex':     q['answerIndex']
            })

    # API 호출 결과 반환
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({'worksheet_code': code, 'questions': mcqs})
    }
