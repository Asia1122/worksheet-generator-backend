import os
import json
import boto3
import http.client

OPENAI_KEY     = os.getenv('OPENAI_API_KEY')
DYNAMODB_TABLE = os.getenv('DYNAMODB_TABLE')

dynamodb = boto3.resource('dynamodb')
table    = dynamodb.Table(DYNAMODB_TABLE)

def call_openai(count, question_type, topic):
    conn = http.client.HTTPSConnection("api.openai.com")

    # 1) 기본 설명
    prompt = (
        f"Generate {count} questions in Korean for elementary school students on the topic '{topic}'. "
        "Questions should be either pure calculation or sentence-form word problems. "
    )

    # 2) 객관식/단답형 옵션
    if question_type == "객관식":
        prompt += (
            "For calculation or word problems, provide 4 options each (no labels like ①–⑤) "
            "and ensure the correct answer is always in option 2, 3, or 4. "
        )
    else:
        prompt += "Do not include any options (short-answer style). "

    # 3) 비율 지정: 계산 80%, 문장제 20%
    prompt += (
        "Make 80% of the questions pure calculation format (e.g., “30 x 4 = ?”, “125 + 354를 구하세요.”) "
        "and 20% sentence-form word problems. "
    )

    # 4) 문장제 형식 예시—형식 참고용, 실제 문제는 반드시 '{topic}' 관련으로 생성
    prompt += (
        "Use these as style examples but adapt each to the selected topic and do not copy them verbatim:\n"
        "- 예서는 오전에 딸기를 232개, 오후에는 143개 땄습니다. 예서가 딴 딸기는 모두 몇 개 인가요?\n"
        "- 오징어 20마리를 4개의 봉지에 똑같이 나누어 담으면 한 봉지에 몇 마리씩 담을 수 있나요?\n"
        "- 채원이는 한 박스에 플라스틱병을 16개씩 담았습니다. 4박스를 가득 담았다면 총 몇 개인가요?\n"
        f"Each new word problem must be concise (max two lines) and use numbers/contexts that reflect '{topic}'. "
    )

    # 5) 조언(advice) 지시
    prompt += (
        "For each question, include a one-line advice that specifically helps solve that exact question. "
        "Return a JSON array of objects with keys: "
        "number (int), stem (string), options (array of strings if any), "
        "answerIndex (0-based) or answer (string), advice (string)."
    )

    payload = json.dumps({
        "model": "gpt-4o-mini",
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
    res  = conn.getresponse()
    body = res.read().decode()
    if res.status != 200:
        raise Exception(f"OpenAI API error {res.status}: {body}")

    data = json.loads(body)
    raw  = data["choices"][0]["message"]["content"]

    # JSON 배열만 추출
    s = raw.find('[')
    e = raw.rfind(']')
    if s < 0 or e < 0:
        raise Exception(f"JSON parsing error: cannot find array delimiters\nRaw response:\n{raw}")

    arr = json.loads(raw[s:e+1])
    if not isinstance(arr, list):
        raise Exception(f"OpenAI response is not a list: {type(arr)}\nRaw response:\n{raw}")

    return arr

def lambda_handler(event, context):
    try:
        body          = json.loads(event.get('body', '{}'))
        topic         = body['topic']
        count         = int(body.get('count', 10))
        question_type = body.get('type', '객관식')
        code          = context.aws_request_id[:8]

        questions = call_openai(count, question_type, topic)

        with table.batch_writer() as batch:
            for q in questions:
                if 'answerIndex' in q:
                    answer_value = q['answerIndex'] + 1
                else:
                    answer_value = q.get('answer', '')

                item = {
                    'worksheet_code' : code,
                    'question_number': q['number'],
                    'question'       : q['stem'],
                    'options'        : q.get('options', []),
                    'answer'         : answer_value,
                    'advice'         : q.get('advice', '')
                }
                batch.put_item(Item=item)

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'worksheet_code': code, 'questions': questions})
        }

    except Exception as e:
        print("Error in lambda_handler:", str(e))
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }
