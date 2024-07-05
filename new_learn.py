import requests
from flask import Flask, render_template, request
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy.orm import sessionmaker
from db_manager import Base, Case, engine
import re
import logging
import json
import os
import pickle
from soynlp.tokenizer import LTokenizer
from soynlp.word import WordExtractor

app = Flask(__name__)

"""전체적인 구조 정리
app = Flask(__name__) 은 Flask(FastAPI랑 비슷한 거)로 웹을 만든다는 걸 뜻합니다
app.run 함수로 실행해야 웹이 실행 되는데, run 함수는 보통 제일 마지막에 호출합니다. 서버가 시작되기 전에 미리미리
데이터 불러오고, 정리하고, 하는 게 좋아요."""


# 터미널에 로그 메세지를 출력할 때 어떤 식으로 출력을 남길지 정하는 코드입니다.
# logging.info("여기다가 할 말 쓰기") 이렇게 하면 print 함수 처럼 터미널에 메세지가 출력 되는데
# 이걸 굳이 쓰는 이유는 코드 중간 중간에 진행 상황을 이런 식으로 출력해주면 어디서 버그가 났는지 알기 쉬워집니다
# 전처리를 완료했을 때 logging.info('전처리 완료, 학습 시작') 이렇게 메세지를 출력해주고, 그리고 학습이 끝나면
# logging.info('학습 완료') 라는 메세지를 전달하게 했어요. 그런데 여기서 '학습 완료'라는 메세지가 안 뜨고 프로그램이 꺼진다면
# 학습 진행 중에 어떤 버그가 있다라는 걸 명확히 알 수 있게 되고, 또 주석처럼 코드 설명을 도와주기도 하기에 여러모로 유용한 로깅입니다
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# API 설정
API_KEY = "D/spYGY15giVS64SLvtShZlNHxAbr9eDi1uU1Ca1wrqCiU+0YMwcnFy53naflVlg5wemikAYwiugNoIepbpexQ=="
API_URL = "https://api.odcloud.kr/api/15069932/v1/uddi:3799441a-4012-4caa-9955-b4d20697b555"

# 캐시 파일입니다, 여기서 캐시는 브라우저에서 캐시 삭제 그런 거랑 같은 용도입니다
# 서버에서 법률 용어집을 불러오고 그 내용을 아래 파일에 저장합니다 
LEGAL_TERMS_CACHE_FILE = "legal_terms_cache.json"

# 매번 실행할 때마다 판례들 문장에서 단어 점수를 계산하면 시간이 너무 오래 걸려서 
# 결과가 나오면 이렇게 캐시 파일로 만들어 저장합니다
WORD_SCORES_CACHE_FILE = 'word_scores.pkl'

# 법률 용어 사전
legal_terms_dict = {}

def get_legal_terms():
    """법률 용어 사전을 서버에 요청해서 가져오는 함수"""
    global legal_terms_dict
    
    #이미 용어 사전을 불러온 상태라면 여기서 멈춰버립니다
    if legal_terms_dict:
        return legal_terms_dict
    
    # 만약 이전에 생성해둔 파일이 있다면 그걸 불러옵니다.
    if os.path.exists(LEGAL_TERMS_CACHE_FILE):
        logging.info("캐시된 법률 용어 데이터 불러오기")
        with open(LEGAL_TERMS_CACHE_FILE, 'r', encoding='utf-8') as f:
            legal_terms_dict = json.load(f)
        logging.info(f"{len(legal_terms_dict)}개의 법률 용어를 캐시에서 불러왔습니다.")
    else:
        logging.info("API에서 법률 용어 데이터 가져오기 시작")

        
        params = {
            "serviceKey": API_KEY,
            "page": 1,
            "perPage": 1000
        }
        response = requests.get(API_URL, params=params)
        if response.status_code == 200:
            data = response.json()
            if 'data' in data:
                legal_terms_dict = {item['용어명']: item['설명'] for item in data['data']}
                logging.info(f"{len(legal_terms_dict)}개의 법률 용어를 가져왔습니다.")
                
                with open(LEGAL_TERMS_CACHE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(legal_terms_dict, f, ensure_ascii=False, indent=2)
                logging.info("법률 용어 데이터를 캐시 파일에 저장했습니다.")
            else:
                logging.error("API 응답에 'data' 키가 없습니다.")
        else:
            logging.error(f"API 요청 실패: 상태 코드 {response.status_code}")
    
    return legal_terms_dict

def load_cases():
    """데이터베이스에서 판례 데이터를 로드하는 함수"""
    
    #DB 기본 설정입니다, Session도 만들고, DB 열고
    Base.metadata.bind = engine
    session = sessionmaker(bind=engine)()

    logging.info("데이터베이스에서 판례 데이터 로딩 시작")

    try:
        
        total_cases = session.query(Case).count()
        logging.info(f"총 {total_cases}개의 판례가 데이터베이스에 있습니다.")

        cases = []
        valid_cases = 0
        for i, case in enumerate(session.query(Case).yield_per(1000)):
            if case.summary and isinstance(case.summary, str) and len(case.summary.strip()) > 0:
                cases.append(case)
                valid_cases += 1
            if (i + 1) % 1000 == 0:
                logging.info(f"{i + 1}/{total_cases} 판례 처리 완료, 유효한 판례: {valid_cases}")

        logging.info(f"총 {len(cases)}개의 유효한 판례를 로드했습니다.")
        return cases

    except Exception as e:
        logging.error(f"데이터 로드 중 오류 발생: {str(e)}")
        return []

    finally:
        session.close()

# 긴 문장을 더 깔끔하게 토큰들로 만들기 위해 요약문을 특수 문자, 이모티콘, 숫자 제거 및 공백 정리를 합니다.
# 여기서 토큰은 문장을 최소 단위로 나눈 것 중 하나를 의미합니다
# 예를 들어 '나는 달리러 갑니다'를 tokenizer('나는 달리러 갑니다') 이 함수로 돌린다고 한다면 결과는 ['나는', '달리러', '갑니다']이 됩니다.
def preprocess_text(text):
    """텍스트 전처리 함수, text에 있는 한글이나 공백 제외하고 특수문자는 전부 제외합니다."""
    text = re.sub(r'[^\w\s]|[ㄱ-ㅎㅏ-ㅣ]+|\d+', '', text)
    return ' '.join(text.split())

def get_word_scores(force_recalculate=False):
    """WordExtractor를 사용하여 단어 점수를 계산하거나 캐시에서 로드하는 함수
    처음 실행할 때는 판례 데이터를 전부 불러와서 단어 점수를 계산합니다. 
    (단어 점수는 단어 응집도, 분기, 주변 단어 다양성, 등장 빈도 등을 고려하여 계산합니다
    예를 들어 어떤 단어가 자주 등장하고, 또 다른 단어와 자주 연결된다면 그 두 단어가 하나의 문장으로 쓰일 수 있음을
    컴퓨터가 알 수 있게 됩니다. 그렇게 하여 자연어를 이해하고, 하는 건데 자세한 건 클로드에게 '
    한국어 언어 처리할 때 단어 점수는 무슨 뜻이야?' 라고 물어보는 걸 추천합니다.)"""
    
    #단어 점수를 계산하기 전에 이전에 단어 점수를 계산한 파일이 있다면 그걸 불러옵니다.
    if not force_recalculate and os.path.exists(WORD_SCORES_CACHE_FILE):
        logging.info("캐시된 word scores 데이터 불러오기")
        #파일 열기
        with open(WORD_SCORES_CACHE_FILE, 'rb') as f:
            word_scores = pickle.load(f)
        logging.info(f"{len(word_scores)}개의 word scores를 캐시에서 불러왔습니다.")
    else: 
        #저장된 파일이 없거나, 혹은 force_recalulate가 True인 경우 밑바닥부터 단어 점수를 계산합니다
        logging.info("Word scores 계산 시작")
        word_extractor = WordExtractor(
            min_frequency=5,
            min_cohesion_forward=0.1,
            min_right_branching_entropy=0.5,
            min_left_branching_entropy=0.5
        )
        word_extractor.train(preprocessed_summaries)
        word_scores = word_extractor.extract()
        
        logging.info(f"{len(word_scores)}개의 word scores를 계산했습니다.")
        
        with open(WORD_SCORES_CACHE_FILE, 'wb') as f:
            pickle.dump(word_scores, f)
        logging.info("Word scores 데이터를 캐시 파일에 저장했습니다.")
    
    return word_scores

def highlight_legal_terms(text):
    """법률 용어를 하이라이트하는 함수"""
    terms = get_legal_terms()
    for term, explanation in terms.items():
        pattern = r'(?<!\w)' + re.escape(term) + r'(?!\w)'
        replacement = f'<span class="legal-term" data-toggle="tooltip" title="{explanation}"><strong>{term}</strong></span>'
        text = re.sub(pattern, replacement, text)
    return text

def calculate_similarity(user_input, case_summary):
    """사용자 입력과 판례 요약 간의 유사도를 계산하는 함수"""
    try:
        #유저가 입력한 문장으로 토큰들을 만들고, 집합(set)로 만들기
        user_tokens = set(tokenize_ko(user_input))
        #판례 요약에 있는 문장으로 토큰들을 만들고, 집합(set)로 만들기
        case_tokens = set(tokenize_ko(case_summary))
        #법률 용어 사전
        legal_terms = set(get_legal_terms().keys())
        
        #유저 토큰과 판례 토큰의 교집합을 구하여 공통되는 토큰이 얼마나 되는지 계산하는 변수입니다
        #common_tokens의 수가 높을 수록 두 문장의 유사하다고 볼 수 있어요.
        common_tokens = user_tokens.intersection(case_tokens)
        legal_term_matches = common_tokens.intersection(legal_terms)
        
        #유사도 점수를 계산합니다 (공통 토큰 수 + 2 * 법률 용어 일치 수) / (전체 토큰 수)
        similarity = len(common_tokens) + 2 * len(legal_term_matches)
        return similarity / (len(user_tokens) + len(case_tokens))
    except Exception as e:
        logging.error(f"유사도 계산 중 오류 발생: {str(e)}")
        return 0

def find_similar_case(user_input, filtered_cases):
    """사용자 입력과 가장 유사한 판례를 찾는 함수"""
    try:
        similarities = [(case, calculate_similarity(user_input, case.summary)) for case in filtered_cases if case.summary]
        if not similarities:
            logging.warning("유사한 케이스를 찾을 수 없습니다.")
            return None
        return max(similarities, key=lambda x: x[1])[0]
    except Exception as e:
        logging.error(f"유사 케이스 검색 중 오류 발생: {str(e)}")
        return None

# 데이터 로드 및 전처리
cases = load_cases()
logging.info(f"로드된 총 케이스 수: {len(cases)}")

summaries = [case.summary for case in cases if case.summary and isinstance(case.summary, str) and len(case.summary.strip()) > 0]
logging.info(f"유효한 summary 수: {len(summaries)}")

preprocessed_summaries = [preprocess_text(summary) for summary in summaries]

# Word scores 계산 또는 로드
word_scores = get_word_scores()

# 단어 필터링
filtered_words = {word: score for word, score in word_scores.items() if 1 < len(word) <= 10}

print(f"필터링 후 단어 수: {len(filtered_words)}")
print("상위 20개 단어와 점수:")
for word, score in sorted(filtered_words.items(), key=lambda x: x[1].cohesion_forward, reverse=True)[:20]:
    print(f"{word}: {score.cohesion_forward}")

# Tokenizer 초기화
tokenizer = LTokenizer(scores={word:score.cohesion_forward for word, score in filtered_words.items()})

def tokenize_ko(text):
    """한국어 텍스트를 토큰화하는 함수"""
    return tokenizer.tokenize(text)

# TF-IDF를 위한 korean_stopwords
# TF는 단어의 빈도라고도 하며, 단어 빈도가 얼마나 자주 등장하는지를 나타냅니다
# IDF는 역문서 빈도라고도 하며 특정 단어가 몇 개의 문서에 나타나는지를 알려줍니다
# TF-IDF는 단어의 빈도와 역문서 빈도를 곱하여 계산합니다. 
korean_stopwords = ['은', '는', '이', '가', '을', '를', '의', '에', '에서', '로', '으로', '와', '과', '도', '만', '에게', '께', '한테', '처럼', '같이']

# TF-IDF 벡터화, 텍스트 데이터를 숫자 벡터로 만들어 컴퓨터가 이해할 수 있게 해줍니다
vectorizer = TfidfVectorizer(tokenizer=tokenize_ko, stop_words=korean_stopwords)

@app.route('/', methods=['GET', 'POST'])
def index():
    """메인 페이지 라우트"""
    if request.method == 'POST':
        #상황 입력받기
        user_input = request.form['situation']
        
        #분야
        legal_fields = request.form.getlist('legal_fields')
        
        logging.info(f"사용자 입력 받음, 선택된 법률 분야: {legal_fields}")
        
        if not legal_fields or '잘모르겠습니다' in legal_fields:
            logging.info("선택된 법률 분야가 없습니다. 모든 분야를 대상으로 검색합니다.")
            filtered_cases = cases
        else:
            filtered_cases = [case for case in cases if case.class_name in legal_fields]
        
        if not filtered_cases:
            logging.warning("해당하는 케이스가 없습니다.")
            return render_template('no_results.html', message="선택된 법률 분야에 해당하는 케이스가 없습니다.")
        
        logging.info("유사 판례 검색 시작")
        case = find_similar_case(user_input, filtered_cases)
        
        if case is None:
            logging.warning("유사한 케이스를 찾을 수 없습니다.")
            return render_template('no_results.html', message="유사한 케이스를 찾을 수 없습니다.")
        
        logging.info("법률 용어 하이라이트 처리 중")
        case.processed_summary = highlight_legal_terms(case.summary)
        case.processed_question = highlight_legal_terms(case.jdgmnQuestion if case.jdgmnQuestion else "")
        case.processed_answer = highlight_legal_terms(case.jdgmnAnswer if case.jdgmnAnswer else "")
        
        logging.info("검색 결과 페이지 렌더링")
        return render_template('result.html', case=case)
    
    legal_fields = list(set(case.class_name for case in cases if case.class_name))
    return render_template('index.html', legal_fields=legal_fields)

@app.route('/search')
def search(): 
    """검색 페이지 라우트"""
    return render_template('search.html')

if __name__ == '__main__':
    app.run(debug=True)