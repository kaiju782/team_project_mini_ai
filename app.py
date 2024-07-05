import requests
from flask import Flask, render_template, request, flash
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy.orm import sessionmaker
from db_manager import Base, Case, engine  # your_models.py에서 정의한 모델을 import
import re
import logging
import json
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)
# 로깅 설정, (asctime는 작성년도,월,일,시,분,초), %(levelname는 info, warning, 등등 로그 레벨
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# API 설정하기
API_KEY = "D/spYGY15giVS64SLvtShZlNHxAbr9eDi1uU1Ca1wrqCiU+0YMwcnFy53naflVlg5wemikAYwiugNoIepbpexQ=="
API_URL = "https://api.odcloud.kr/api/15069932/v1/uddi:3799441a-4012-4caa-9955-b4d20697b555"

# 법률 용어 사전을 여기다 담습니다
legal_terms_dict = {}

# 법률 용어 사전 파일은 여기 이 파일에 저장 됩니다
CACHE_FILE = "legal_terms_cache.json"

# 법률 용어 가져오기(법률 용어를 서버에 요청해서 가져왔는데, 불러온 거 파일에 저장하게 했습니다)
def get_legal_terms():
    global legal_terms_dict
    
    #이미 법률 용어 사전에 뭔가 들어있다면, 그냥 있는 거 반환하기
    if legal_terms_dict:
        return legal_terms_dict
    
    #만약 용어 사전 변수가 비어있다면
    #그리고 만약 이전에 저장했던 용어 사전 파일이 있다면    
    if os.path.exists(CACHE_FILE):
        logging.info("저장된 용어 사전 불러오기")
        #utf-8로 CACHE_FILE 열기 (한국어는 utf-8 필수)
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            legal_terms_dict = json.load(f)
        #불러오기 성공!
        logging.info(f"{len(legal_terms_dict)}개의 법률 용어를 캐시에서 불러왔습니다.")
    else:
        #만약 용어 사진 파일이 없다면
        logging.info("API에서 법률 용어 데이터 가져오기 시작")
        params = {
            "serviceKey": API_KEY,
            "page": 1,
            "perPage": 1000
        }
        #공공 오픈 데이터 API에서 제공해준 URL에 패킷을 보냅니다, params는 여기에는 요청하는 이의 정보나
        #요청하는 사람이 원하는 파일 형태를 담고 있습니다
        response = requests.get(API_URL, params=params)
        
        #200이면 사이트에서 응답 했다는 뜻
        if response.status_code == 200:
            data = response.json()
            #data에 'data'라는 딕셔너리가 있다면
            if 'data' in data:
                legal_terms_dict = {item['용어명']: item['설명'] for item in data['data']}
                logging.info(f"{len(legal_terms_dict)}개의 법률 용어를 가져왔습니다.")
                
                # 캐시 파일에 저장
                with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(legal_terms_dict, f, ensure_ascii=False, indent=2)
                logging.info("법률 용어 데이터를 캐시 파일에 저장했습니다.")
            else:
                logging.error("API 응답에 'data' 키가 없습니다.")
        else:
            logging.error(f"API 요청 실패: 상태 코드 {response.status_code}")
    
    return legal_terms_dict

# 데이터베이스 파일 불러오기
def load_cases():
    # 데이터베이스 연결 설정
    Base.metadata.bind = engine
    DBSession = sessionmaker(bind=engine)
    session = DBSession()

    logging.info("데이터베이스에서 판례 데이터 로딩 시작")

    try:
        # 전체 판례(case) 수 조회
        total_cases = session.query(Case).count()
        logging.info(f"총 {total_cases}개의 판례가 데이터베이스에 있습니다.")

        # 판례(session.query(Case)) 정보 불러오기
        cases = []
        
        # yield_per는 DB에서 한 번에 1000개의 레코드(데이터 항목)만 가져오도록 지시하는 함수입니다
        # 한 번에 많은 데이터를 불러오면 부하가 올 수 있기 때문에 분산해서 불러와야 좋아요. 
        # enumerate 는 현재 처리 중인 레코드 번호를 알 수 있게 해줍니다
        for i, case in enumerate(session.query(Case).yield_per(1000)):
            cases.append(case)
            if (i + 1) % 1000 == 0:
                logging.info(f"{i + 1}/{total_cases} 판례 로드 완료")

        logging.info(f"총 {len(cases)}개의 판례를 로드했습니다.")
        return cases

    except Exception as e:
        logging.error(f"데이터 로드 중 오류 발생: {str(e)}")
        return []

    finally:
        session.close()
        
cases = load_cases()

# 벡터화 준비하기
# 텍스트 데이터들(자연어)을 벡터로 변환해서 컴퓨터가 읽을 수 있게 준비하기
vectorizer = TfidfVectorizer()
# 판례 요약문을 전부 모아서 학습하기. 
# fit_transform에서 fit는 입력 데이터로 어휘 학습하기, transform은 학습된 어휘로 입력된 데이터 TF-IDF 벡터로 변환하기
tfidf_matrix = vectorizer.fit_transform([case.summary for case in cases if case.summary])

# 법률 용어 볼드체 처리하기, 
def highlight_legal_terms(text):
    terms = get_legal_terms()
    for term, explanation in terms.items():
        pattern = r'\b' + re.escape(term) + r'\b'
        replacement = f'<span class="legal-term" data-toggle="tooltip" title="{explanation}"><strong>{term}</strong></span>'
        text = re.sub(pattern, replacement, text)
    return text


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        user_input = request.form['situation'] # 사용자가 입력한 문의
        legal_fields = request.form.getlist('legal_fields')  # 체크박스에서 선택된 법률 분야들
        if user_input == '' or len(user_input) <= 3:
            flash('검색어가 없거나 너무 짧습니다')
            return render_template('search.html')
            
        logging.info(f"사용자 입력 받음, 선택된 법률 분야: {legal_fields}")
        
        if not legal_fields or legal_fields == '잘모르겠습니다':
            logging.info("선택된 법률 분야가 없습니다. 모든 분야를 대상으로 검색합니다.")
            filtered_cases = cases
        else:
            # 선택된 법률 분야에 해당하는 케이스만 필터링
            filtered_cases = [case for case in cases if case.class_name in legal_fields]
        
        # 필터링된 케이스들로 TF-IDF 매트릭스 재구성
        filtered_tfidf_matrix = vectorizer.transform([case.summary for case in filtered_cases if case.summary])
        
        logging.info("유사 판례 검색 시작")
        #유저가 입력한 텍스트 벡터화 하기
        user_vector = vectorizer.transform([user_input])
        
        #코사인 유사도 계산으로 두 벡터 비교하기(https://wikidocs.net/24603)
        similarities = cosine_similarity(user_vector, filtered_tfidf_matrix)
        
        #제일 비슷한 판례 아이디
        most_similar_idx = similarities.argmax()
        
        #제일 비슷한 판레 가져요기
        case = filtered_cases[most_similar_idx]
        
        logging.info("법률 용어 하이라이트 처리 중")
        case.processed_summary = highlight_legal_terms(case.summary)
        case.processed_question = highlight_legal_terms(case.jdgmnQuestion if case.jdgmnQuestion else "")
        case.processed_answer = highlight_legal_terms(case.jdgmnAnswer if case.jdgmnAnswer else "")
        logging.info("검색 결과 페이지 렌더링")
        return render_template('result.html', case=case)
    
    # GET 요청 시 메인페이지를 보여줌, 인자는 법률 분야 목록을 전달
    legal_fields = list(set(case.class_name for case in cases if case.class_name))
    return render_template('index.html', legal_fields=legal_fields)
    
@app.route('/search')
def search(): 
    return render_template('search.html')  # or any appropriate response

if __name__ == '__main__':
    app.run(debug=True)