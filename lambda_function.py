import os
import json
import boto3
import http.client

# 환경 변수
OPENAI_KEY = os.getenv('OPENAI_API_KEY')
DYNAMODB_TABLE = os.getenv('DYNAMODB_TABLE')

# DynamoDB 리소스 초기화
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(DYNAMODB_TABLE)

def call_openai(count, question_type, topic):
    """
    OpenAI GPT-4를 호출하여 지정된 유형과 주제의 문제를 생성하고,
    JSON 배열 형태로 반환합니다.
    """
    # 프롬프트 구성
    prompt = f"Generate {count} questions in Korean for elementary school students on the topic '{topic}'. "
    if question_type == "객관식":
        prompt += "Make them multiple-choice with 4 options each, labeled ① to ④. "
    elif question_type == "단답형":
        prompt += "Make them short-answer questions (no options). "
    else:  # 반반
        prompt += "Make half multiple-choice with 4 options each (①–④) and half short-answer. "
    prompt += (
        "Include a mix of word problems and simple calculations. "
        "Return a JSON array of objects with keys: number, stem, options (list, if any), "
        "answerIndex (for multiple-choice) or answer (for short-answer)."
    )

    # API 요청 페이로드
    payload = json.dumps({
        "model": "gpt-4",
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

    # HTTPS 연결 및 요청
    conn = http.client.HTTPSConnection("api.openai.com")
    conn.request("POST", "/v1/chat/completions", payload, headers)
    res = conn.getresponse()
    body = res.read().decode()

    # 상태 코드 체크
    if res.status != 200:
        print(f"OpenAI API error {res.status}: {body}")
        raise Exception(f"OpenAI API responded {res.status}")

    # 응답 JSON 파싱
    resp = json.loads(body)
    raw = resp["choices"][0]["message"]["content"]

    # JSON 배열 부분만 추출
    start = raw.find('[')
    end   = raw.rfind(']')
    if start == -1 or end == -1:
        print("JSON parsing error, content:", raw)
        raise Exception("Could not find JSON array in response")
    json_str = raw[start:end+1]
    return json.loads(json_str)


def lambda_handler(event, context):
    try:
        # 요청 본문 파싱
        body = json.loads(event.get('body', '{}'))
        question_type = body.get('type', '객관식')
        topic         = body['topic']
        count         = int(body.get('count', 10))
        code          = context.aws_request_id[:8]

        # 문제 생성
        questions = call_openai(count, question_type, topic)

        # DynamoDB에 저장
        with table.batch_writer() as batch:
            for q in questions:
                item = {
                    'worksheet_code': code,
                    'question_number': q['number'],
                    'question': q['stem']
                }
                # 객관식
                if question_type == '객관식' or ('options' in q and 'answerIndex' in q):
                    item['options'] = q.get('options', [])
                    item['answer'] = q.get('answerIndex', 0) + 1
                else:
                    # 단답형
                    item['answer'] = q.get('answer')
                batch.put_item(Item=item)

        # 성공 응답
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
