import os, json, boto3, http.client

OPENAI_KEY     = os.getenv('OPENAI_API_KEY')
DYNAMODB_TABLE = os.getenv('DYNAMODB_TABLE')

dynamodb = boto3.resource('dynamodb')
table    = dynamodb.Table(DYNAMODB_TABLE)

def call_openai(count, question_type, topic):
    conn = http.client.HTTPSConnection("api.openai.com")

    # 프롬프트 조립
    prompt = f"Generate {count} questions in Korean for elementary school students on the topic '{topic}'. "
    if question_type == "객관식":
        prompt += "Make them multiple-choice with 4 options each (no labels like ①–⑤). "
    elif question_type == "단답형":
        prompt += "Make them short-answer questions (no options). "
    else:  # 반반
        prompt += (
            "Make half multiple-choice with 4 options each (no labels) "
            "and half short-answer questions. "
        )
    prompt += "Include a mix of sentence-form problems, simple arithmetic, and formula-only problems such as '354+223 = ?'. "
    prompt += "Return a JSON array of objects with keys: number (int), stem (string), "
    prompt += "options (array of strings, if any), answerIndex (0-based) or answer (string) for short answers."

    payload = json.dumps({
        "model": "gpt-4",
        "messages": [
            {"role":"system","content":"You are a helpful teacher."},
            {"role":"user","content":prompt}
        ],
        "temperature": 0.7
    })
    headers = {
        'Content-Type':'application/json',
        'Authorization': f'Bearer {OPENAI_KEY}'
    }
    conn.request("POST", "/v1/chat/completions", payload, headers)
    res  = conn.getresponse()
    body = res.read().decode()
    if res.status != 200:
        print(f"OpenAI error {res.status}: {body}")
        raise Exception("OpenAI API 에러")
    data = json.loads(body)
    raw  = data["choices"][0]["message"]["content"]

    # JSON 배열만 추출
    s = raw.find('['); e = raw.rfind(']')
    if s<0 or e<0:
        print("JSON parsing error:", raw)
        raise Exception("JSON 배열을 찾을 수 없습니다.")
    arr = json.loads(raw[s:e+1])
    return arr

def lambda_handler(event, context):
    try:
        body         = json.loads(event.get('body','{}'))
        topic        = body['topic']
        count        = int(body.get('count',10))
        question_type= body.get('type','객관식')
        code         = context.aws_request_id[:8]

        questions = call_openai(count, question_type, topic)

        with table.batch_writer() as batch:
            for q in questions:
                item = {
                    'worksheet_code':  code,
                    'question_number': q['number'],
                    'question':        q['stem']
                }
                if question_type == "단답형":
                    item['answer'] = q.get('answer','')
                else:
                    item['options']     = q.get('options',[])
                    item['answerIndex'] = q.get('answerIndex',0) + 1  # 1-based
                batch.put_item(Item=item)

        return {
            'statusCode':200,
            'headers':{'Content-Type':'application/json'},
            'body':json.dumps({'worksheet_code':code,'questions':questions})
        }
    except Exception as e:
        print("Error:",str(e))
        return {
            'statusCode':500,
            'headers':{'Content-Type':'application/json'},
            'body':json.dumps({'error':str(e)})
        }
