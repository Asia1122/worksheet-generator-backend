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

    # 프롬프트 조립
    prompt = (
        f"Generate {count} questions in Korean for elementary school students on the topic '{topic}'. "
        # 객관식/단답형 지시(기존)
    )
    if question_type == "객관식":
        prompt += "Make them multiple-choice with 4 options each (no labels like ①–⑤). "
        # 정답 인덱스(0-based) 조정
        prompt += (
            "For multiple-choice, ensure the correct answer is never the first option; "
            "it should be uniformly among options 2, 3, or 4. "
        )
    elif question_type == "단답형":
        prompt += "Make them short-answer questions (no options). "
    else:  # 반반
        prompt += (
            "Make half multiple-choice with 4 options each (no labels) "
            "and half short-answer questions. "
            "For the multiple-choice half, ensure correct answers are only options 2, 3, or 4. "
        )

    # 분포 조정: 계산 80%, 문장제 20%
    prompt += (
        "Of the total questions, 80% should be pure arithmetic calculation problems "
        "and 20% should be short, two-line max sentence-form word problems. "
        "Word problem examples:\n"
        "- 예서는 오전에 딸기를 232개, 오후에는 143개 땄습니다. 예서가 딴 딸기는 모두 몇 개 인가요?\n"
        "- 오징어 20마리를 4개의 봉지에 똑같이 나누어 담으면 한 봉지에 몇 마리씩 담을 수 있나요?\n"
        "- 채원이는 한 박스에 플라스틱병을 16개씩 담았습니다. 4박스를 가득 담았다면 플라스틱병은 총 몇개 인가요?\n"
    )

    # advice 요청 포함
    prompt += (
        "Include a mix of calculation and word problems as above. "
        "Return a JSON array of objects with keys: "
        "number (int), stem (string), options (array of strings, if any), "
        "answerIndex (0-based) or answer (string) for short answers, "
        "advice (string): a one-line study tip for each question."
    )

    payload = json.dumps({
        "model": "gpt-4o-mini",
        "messages": [
            {"role":"system","content":"You are a helpful teacher."},
            {"role":"user","content":prompt}
        ],
        "temperature": 0.7
    })
def lambda_handler(event, context):
    try:
        body          = json.loads(event.get('body','{}'))
        topic         = body['topic']
        count         = int(body.get('count',10))
        question_type = body.get('type','객관식')
        code          = context.aws_request_id[:8]

        questions = call_openai(count, question_type, topic)

        with table.batch_writer() as batch:
            for q in questions:
                # 객관식·단답형 모두 'answer' 필드에 저장
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
                    # advice 필드 추가
                    'advice'         : q.get('advice', '')
                }
                batch.put_item(Item=item)

        return {
            'statusCode': 200,
            'headers': {'Content-Type':'application/json'},
            'body': json.dumps({'worksheet_code': code, 'questions': questions})
        }

    except Exception as e:
        print("Error:", str(e))
        return {
            'statusCode': 500,
            'headers': {'Content-Type':'application/json'},
            'body': json.dumps({'error': str(e)})
        }
