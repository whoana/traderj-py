# 파이썬으로 배우는 알고리즘 트레이딩 - Part 2: 실전편 (Ch.10~19)

## 학습 개요

이 실전편은 국내 3대 증권사(대신증권, 이베스트투자증권, 키움증권) API를 활용한 자동매매 시스템 구축을 다룬다.
Pandas/matplotlib/PyQt 등 핵심 라이브러리를 익히고, Zipline을 이용한 백테스팅, SQLite 기반 데이터 관리를 거쳐
최종적으로 키움증권 API 기반의 실전 자동매매 프로그램(PyTrader)을 완성한다.
거래량 분석, 업종별 PER, 이동평균선, 급등주 포착, 배당률 기반 투자 등 다양한 트레이딩 전략을 구현한다.

---

## Ch.10 대신증권 API

### 핵심 내용
- **CYBOS Plus**: 대신증권이 제공하는 API 서비스. 국내 증권 API 중 가장 오래되고 사용자가 많음
- **COM 객체 기반**: Windows COM Object를 통해 파이썬에서 접근 (win32com.client.Dispatch 사용)
- **개발 환경**: 대신증권 계좌 개설 -> CYBOS Plus 설치 -> CYBOS 5에서 [CYBOS Plus] 탭으로 로그인
- **API 구조**: 기초 API(연결상태/주식코드) -> 기본 API(종목코드/과거데이터/PER/EPS) -> 알고리즘 -> 매수/매도

### 주요 API/코드 패턴

```python
# COM 객체 생성 패턴
import win32com.client

# 연결 상태 확인
instCpCybos = win32com.client.Dispatch("CpUtil.CpCybos")
print(instCpCybos.IsConnect)  # 0: 미연결, 1: 연결

# 종목 코드 조회
instCpStockCode = win32com.client.Dispatch("CpUtil.CpStockCode")
code = instCpStockCode.NameToCode("삼성전자")  # 종목명 -> 코드

# 과거 데이터 조회 (StockChart 클래스 - CpSysDib 모듈)
instStockChart = win32com.client.Dispatch("CpSysDib.StockChart")
instStockChart.SetInputValue(0, "A003540")  # 종목코드
instStockChart.SetInputValue(1, ord('2'))   # 개수로 요청
instStockChart.SetInputValue(4, 100)        # 요청 개수
instStockChart.SetInputValue(5, [0,2,3,4,5,8])  # 날짜/시/고/저/종/거래량
instStockChart.SetInputValue(6, ord('D'))   # 일봉
instStockChart.BlockRequest()

# PER 조회 (MarketEye 클래스 - 여러 종목 한번에)
instMarketEye = win32com.client.Dispatch("CpSysDib.MarketEye")
instMarketEye.SetInputValue(0, [67, 70])   # PER, EPS 필드
instMarketEye.SetInputValue(1, codeList)    # 종목코드 리스트
instMarketEye.BlockRequest()

# 매수/매도 주문
instCpTdNew5331A = win32com.client.Dispatch("CpTrade.CpTd5331A")
```

### 실전 활용 포인트
- CYBOS Plus는 반드시 **관리자 권한**으로 실행해야 함
- `SetInputValue` -> `BlockRequest` -> `GetHeaderValue/GetDataValue` 패턴이 모든 API 호출의 기본
- **거래량 분석**: 당일 거래량이 과거 평균 대비 1,000% 이상이면 "대박주" 후보로 판별
- **업종별 PER 분석**: MarketEye 클래스로 업종 내 종목들의 PER을 비교하여 저평가 종목 발굴

---

## Ch.11 이베스트투자증권 API

### 핵심 내용
- **xingAPI**: 이베스트투자증권(구 이트레이딩증권)이 제공하는 API. 낮은 수수료가 장점
- **COM 객체 기반**: 대신증권과 마찬가지로 COM 방식 사용
- **DevCenter**: xingAPI 전용 개발 도구. TR(Transaction) 조회/테스트 가능
- **데이터 유형**: 단일 데이터(Header), 반복 데이터(Occurs), 차트 데이터

### 주요 API/코드 패턴

```python
import win32com.client

# xingAPI 서버 연결 및 로그인
instXASession = win32com.client.Dispatch("XA_Session.XASession")
instXASession.ConnectServer("hts.ebestsec.co.kr", 20001)
instXASession.Login(id, pwd, cert_pwd, 0, False)

# 계좌 조회
accCount = instXASession.GetAccountListCount()
acc = instXASession.GetAccountList(0)

# TR 데이터 조회 (XAQuery 사용)
instXAQuery = win32com.client.Dispatch("XA_DataSet.XAQuery")
instXAQuery.ResFileName = "C:\\eBEST\\xingAPI\\Res\\t1102.res"  # 주식 현재가 조회
instXAQuery.SetFieldData("t1102InBlock", "shcode", 0, "005930")  # 삼성전자
instXAQuery.Request(False)

# 단일 데이터 조회: GetFieldData("OutBlock", "필드명", 0)
# 반복 데이터 조회: GetFieldData("OutBlock1", "필드명", index)
# 차트 데이터: t8410 TR 사용 (일/주/월봉 차트)
```

### 실전 활용 포인트
- **DevCenter**에서 TR별 입력/출력 필드를 확인하고 테스트한 후 코드 작성
- 주요 TR: `t1102`(주식 현재가), `t8410`(차트 데이터), `t0424`(잔고 조회)
- 단일 데이터는 OutBlock, 반복 데이터는 OutBlock1에서 가져옴
- 이벤트 기반 처리: `OnReceiveData` 이벤트로 서버 응답 수신

---

## Ch.12 키움증권 API

### 핵심 내용
- **Open API+**: 키움증권이 제공하는 API. 국내 개인 트레이더들이 가장 많이 사용
- **PyQt 필수**: 키움 Open API+는 OCX(ActiveX) 컨트롤 기반이므로 PyQt의 QAxWidget 필요
- **KOA Studio**: 키움증권 제공 개발 도구. TR 조회/테스트, 화면번호별 데이터 확인
- **모의투자**: 실전 전 반드시 모의투자 서버에서 테스트

### 주요 API/코드 패턴

```python
import sys
from PyQt5.QtWidgets import *
from PyQt5.QAxContainer import *

class Kiwoom(QAxWidget):
    def __init__(self):
        super().__init__()
        self.setControl("KHOPENAPI.KHOpenAPICtrl.1")  # OCX 컨트롤 로드

        # 이벤트 연결
        self.OnEventConnect.connect(self._event_connect)
        self.OnReceiveTrData.connect(self._receive_tr_data)

    # 로그인
    def comm_connect(self):
        self.dynamicCall("CommConnect()")  # 로그인 창 호출

    # 로그인 이벤트 처리
    def _event_connect(self, err_code):
        if err_code == 0:
            print("로그인 성공")

    # TR 데이터 요청
    def set_input_value(self, id, value):
        self.dynamicCall("SetInputValue(QString, QString)", id, value)

    def comm_rq_data(self, rqname, trcode, next, screen_no):
        self.dynamicCall("CommRqData(QString, QString, int, QString)",
                         rqname, trcode, next, screen_no)

    # TR 데이터 수신 이벤트
    def _receive_tr_data(self, screen_no, rqname, trcode, record_name, next, ...):
        if rqname == "opt10081_req":  # 일봉 데이터
            data_cnt = self.dynamicCall("GetRepeatCnt(QString, QString)", trcode, rqname)
            for i in range(data_cnt):
                date = self.dynamicCall("GetCommData(QString, QString, int, QString)",
                                        trcode, rqname, i, "일자")
                close = self.dynamicCall("GetCommData(QString, QString, int, QString)",
                                         trcode, rqname, i, "현재가")

    # 종목 코드 조회
    def get_code_list_by_market(self, market):
        code_list = self.dynamicCall("GetCodeListByMarket(QString)", market)
        return code_list.split(';')

    # 종목명 조회
    def get_master_code_name(self, code):
        return self.dynamicCall("GetMasterCodeName(QString)", code)
```

### 실전 활용 포인트
- **이벤트 기반 프로그래밍**: 요청(Request) -> 이벤트(Event) -> 콜백(Callback) 패턴
- `SetInputValue` -> `CommRqData` -> `OnReceiveTrData` 이벤트에서 `GetCommData`로 데이터 수신
- 화면번호(screen_no)로 TR 요청 관리 (최대 200개)
- 주요 TR: `opt10081`(주식일봉차트조회), `opt10001`(주식기본정보), `opw00001`(예수금상세현황)
- **KOA Studio**에서 TR 구조 확인 필수: Input/Output 필드, 반복횟수 등

---

## Ch.13 Pandas를 이용한 데이터 분석 기초

### 핵심 내용
- **Series**: 1차원 배열 형태의 자료구조. 인덱스-값 쌍으로 구성
- **DataFrame**: 2차원 테이블 형태. 행(인덱스)과 열(칼럼)로 구성. 주식 데이터 다루기에 최적
- **DataReader**: `pandas_datareader`를 이용해 Yahoo Finance 등에서 주식 데이터 자동 다운로드
- **이동평균선**: 일정 기간 동안의 주가를 산술 평균한 값을 연결한 선

### 주요 API/코드 패턴

```python
import pandas as pd
from pandas_datareader import data as pdr

# Series 생성
s = pd.Series([1, 2, 3, 4], index=['a', 'b', 'c', 'd'])

# DataFrame 생성 및 칼럼/로우 선택
df = pd.DataFrame({'Open': [100, 102], 'Close': [101, 103]})
df['Close']          # 칼럼 선택
df.loc[0]            # 로우 선택 (라벨 기반)
df.iloc[0]           # 로우 선택 (정수 기반)

# 주식 데이터 다운로드
df = pdr.DataReader("005930.KS", "yahoo", "2020-01-01", "2020-12-31")

# 이동평균선 계산
df['MA5'] = df['Close'].rolling(window=5).mean()    # 5일 이동평균
df['MA20'] = df['Close'].rolling(window=20).mean()  # 20일 이동평균
df['MA60'] = df['Close'].rolling(window=60).mean()  # 60일 이동평균

# 차트 그리기
df[['Close', 'MA5', 'MA20']].plot()
```

### 실전 활용 포인트
- `rolling(window=N).mean()`으로 N일 이동평균선을 간단하게 계산
- 골든크로스(단기 MA가 장기 MA를 상향 돌파) / 데드크로스(하향 돌파) 신호 감지에 활용
- DataFrame의 `to_csv()`, `read_csv()`로 주가 데이터 파일 입출력
- DataReader로 해외 주식(Yahoo Finance), 국내 주식(KRX) 데이터 모두 수집 가능

---

## Ch.14 Pandas와 Zipline을 이용한 백테스팅

### 핵심 내용
- **백테스팅(Backtesting)**: 개발한 투자 알고리즘을 과거 데이터로 검증하는 과정
- **Zipline**: Quantopian이 개발한 오픈소스 알고리즘 트레이딩 라이브러리
- **핵심 함수**: `initialize(context)` - 초기 설정, `handle_data(context, data)` - 매 거래일 실행되는 트레이딩 로직
- **유가증권/코스닥 백테스팅**: 국내 주식 데이터를 Zipline 번들로 등록하여 백테스트

### 주요 API/코드 패턴

```python
from zipline.api import order, record, symbol, set_commission, set_slippage
from zipline import run_algorithm
import pandas as pd

def initialize(context):
    context.i = 0
    context.asset = symbol('AAPL')
    set_commission(commission.PerShare(cost=0.0075))  # 수수료 설정

def handle_data(context, data):
    context.i += 1
    if context.i < 20:
        return

    # 이동평균선 전략
    short_mavg = data.history(context.asset, 'price', bar_count=5, frequency='1d').mean()
    long_mavg = data.history(context.asset, 'price', bar_count=20, frequency='1d').mean()

    # 골든크로스 매수
    if short_mavg > long_mavg:
        order(context.asset, 10)
    # 데드크로스 매도
    elif short_mavg < long_mavg:
        order(context.asset, -10)

    record(AAPL=data.current(context.asset, 'price'),
           short_mavg=short_mavg, long_mavg=long_mavg)

# 백테스트 실행
result = run_algorithm(
    start=pd.Timestamp('2020-01-01', tz='utc'),
    end=pd.Timestamp('2020-12-31', tz='utc'),
    initialize=initialize,
    handle_data=handle_data,
    capital_base=10000000,  # 초기 자본금 1천만원
    bundle='quantopian-quandl'
)
```

### 실전 활용 포인트
- `initialize`에서 수수료(`set_commission`), 슬리피지(`set_slippage`), 초기 자본금 설정
- `handle_data`에서 `data.history()`로 과거 데이터 조회, `order()`로 주문 실행
- `record()`로 기록한 데이터를 나중에 matplotlib으로 시각화
- 국내 주식 백테스팅 시 한국 거래소 캘린더와 데이터 번들 별도 설정 필요
- 전략 성과 지표: 수익률, 최대 낙폭(MDD), 샤프 비율 등 확인

---

## Ch.15 matplotlib를 이용한 데이터 시각화

### 핵심 내용
- **pyplot**: matplotlib의 핵심 모듈. MATLAB과 유사한 인터페이스 제공
- **Figure/Subplot**: 하나의 Figure에 여러 Subplot 배치 가능 (주가+거래량 동시 표시)
- **캔들스틱 차트**: 일봉(시가/고가/저가/종가)을 봉 형태로 표현. mplfinance 라이브러리 활용
- **다양한 차트**: 라인, 바(bar), 파이(pie) 차트

### 주요 API/코드 패턴

```python
import matplotlib.pyplot as plt
from pandas_datareader import data as pdr
import mplfinance as mpf

# 기본 라인 차트
df = pdr.DataReader("005930.KS", "yahoo", "2020-01-01", "2020-12-31")
plt.figure(figsize=(12, 6))
plt.plot(df.index, df['Close'], label='종가')
plt.title('삼성전자 주가')
plt.xlabel('날짜')
plt.ylabel('가격')
plt.legend()
plt.show()

# 수정종가 + 거래량 동시 표시 (subplot 활용)
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={'height_ratios': [3, 1]})
ax1.plot(df['Adj Close'])
ax1.set_ylabel('수정종가')
ax2.bar(df.index, df['Volume'])
ax2.set_ylabel('거래량')
plt.tight_layout()

# 캔들스틱 차트 (mplfinance)
mpf.plot(df, type='candle', volume=True, style='charles',
         title='삼성전자', ylabel='가격', ylabel_lower='거래량')

# bar 차트
plt.bar(x_labels, values)

# pie 차트
plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90)
```

### 실전 활용 포인트
- 캔들스틱 차트에서 양봉(종가>시가, 빨강)과 음봉(종가<시가, 파랑) 구분
- `gridspec_kw`로 subplot 크기 비율 조정하여 주가/거래량 차트 비율 맞춤
- mplfinance(구 mpl_finance)로 캔들차트를 간편하게 생성
- 이동평균선을 주가 차트 위에 오버레이하여 매매 시점 시각화
- pie 차트로 포트폴리오 비중, bar 차트로 종목별 수익률 비교

---

## Ch.16 PyQt를 이용한 GUI 프로그래밍

### 핵심 내용
- **PyQt**: Qt GUI 프레임워크의 파이썬 바인딩. 크로스 플랫폼 GUI 개발 가능
- **Qt Designer**: 드래그 앤 드롭으로 UI를 설계하는 전용 도구. 아나콘다에 기본 포함
- **기본 위젯**: QPushButton, QLabel, QLineEdit, QRadioButton, QCheckBox, QSpinBox, QTableWidget
- **Layout**: QHBoxLayout(수평), QVBoxLayout(수직), QGridLayout(격자) 배치
- **다이얼로그**: QMessageBox, QFileDialog 등 대화상자
- **matplotlib 연동**: FigureCanvas를 PyQt 위젯에 임베딩

### 주요 API/코드 패턴

```python
import sys
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *

class MyWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyTrader")
        self.setGeometry(300, 300, 400, 300)

        # 위젯 생성
        btn = QPushButton("매수", self)
        btn.clicked.connect(self.btn_clicked)

        label = QLabel("종목코드:", self)
        self.lineEdit = QLineEdit(self)

        # 테이블 위젯 (잔고/종목 표시용)
        self.tableWidget = QTableWidget(self)
        self.tableWidget.setRowCount(10)
        self.tableWidget.setColumnCount(5)
        self.tableWidget.setHorizontalHeaderLabels(['종목코드','종목명','수량','매입가','현재가'])

        # Layout 배치
        layout = QVBoxLayout()
        layout.addWidget(label)
        layout.addWidget(self.lineEdit)
        layout.addWidget(btn)
        layout.addWidget(self.tableWidget)

        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

    def btn_clicked(self):
        code = self.lineEdit.text()
        print(f"매수 주문: {code}")

# Qt Designer에서 만든 .ui 파일 로드
from PyQt5 import uic
form_class = uic.loadUiType("mywindow.ui")[0]

# matplotlib 연동
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

class ChartWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.fig = Figure()
        self.canvas = FigureCanvas(self.fig)
```

### 실전 활용 포인트
- Qt Designer로 UI 설계 -> `.ui` 파일 -> `uic.loadUiType()`으로 파이썬에서 로드
- QTableWidget으로 보유종목/잔고 테이블 구현
- 시그널-슬롯 메커니즘: `btn.clicked.connect(self.handler)` 패턴으로 이벤트 처리
- matplotlib FigureCanvas를 PyQt 위젯에 넣어 실시간 차트 표시
- QTimer로 주기적 데이터 갱신 (자동매매 시 호가/체결 모니터링)

---

## Ch.17 주가 데이터 저장하기

### 핵심 내용
- **SQLite**: 서버 불필요한 경량 DB. 파이썬 표준 라이브러리 `sqlite3`로 바로 사용 가능
- **DB 브라우저**: SQLite DB 파일을 GUI로 확인하는 도구 (DB Browser for SQLite)
- **Pandas + SQLite**: `to_sql()`로 DataFrame을 DB에 저장, `read_sql()`로 DB에서 DataFrame으로 로드
- **증권사 API 연동**: 종목코드 리스트 조회 -> 일봉 연속 조회 -> DB 저장 파이프라인

### 주요 API/코드 패턴

```python
import sqlite3
import pandas as pd

# SQLite 기본 사용
con = sqlite3.connect("stock.db")
cursor = con.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS daily_price "
               "(code TEXT, date TEXT, open INT, high INT, low INT, close INT, volume INT)")
cursor.execute("INSERT INTO daily_price VALUES (?,?,?,?,?,?,?)",
               ('005930', '2020-01-02', 55000, 56000, 54500, 55500, 1000000))
con.commit()
con.close()

# Pandas DataFrame -> SQLite 저장 (to_sql)
con = sqlite3.connect("stock.db")
df.to_sql('daily_price', con, if_exists='append', index=False)

# SQLite -> Pandas DataFrame 로드 (read_sql)
df = pd.read_sql("SELECT * FROM daily_price WHERE code='005930'",
                  con, index_col='date')

# 증권사 API를 이용한 전체 종목 일봉 데이터 저장
codes = kiwoom.get_code_list_by_market("0")  # 유가증권 전 종목
for code in codes:
    # 일봉 데이터 연속 조회 (opt10081 TR)
    kiwoom.set_input_value("종목코드", code)
    kiwoom.set_input_value("기준일자", "20201231")
    kiwoom.set_input_value("수정주가구분", "1")
    kiwoom.comm_rq_data("opt10081_req", "opt10081", 0, "0101")
    # ... 연속 조회 처리 및 DataFrame 변환 후 DB 저장
```

### 실전 활용 포인트
- `to_sql(if_exists='replace'|'append'|'fail')`로 기존 데이터 처리 방식 지정
- 일봉 연속 조회 시 서버 과부하 방지를 위해 `time.sleep()` 필수 (키움: 3.6초 이상 권장)
- 전체 종목 일봉 데이터를 한번 DB에 저장해두면 이후 분석/백테스팅 시 API 호출 없이 활용
- SQLite 파일 하나로 전체 주가 데이터 관리 가능 (가볍고 이식성 좋음)
- `CREATE TABLE IF NOT EXISTS`로 중복 테이블 생성 방지

---

## Ch.18 실전 프로그램 개발 (개발 1~4일차)

### 핵심 내용
- **자동 버전 처리**: 키움 OpenAPI+ 접속 시 버전 업데이트 자동 처리 스크립트
- **윈도우 작업 스케줄러**: 장 시작 전 자동으로 프로그램 실행 설정
- **PyTrader 구현**: 키움 API + PyQt GUI를 결합한 실전 자동매매 프로그램
- **키움 자동 로그인**: 비밀번호 입력 없이 자동 로그인 구현 (계좌비밀번호 저장)
- **매수 테스트 / 잔고 조회 / 자동 주문**: 실제 주문 실행 및 포트폴리오 관리

### 주요 API/코드 패턴

```python
# PyTrader 기본 구조 (Kiwoom.py + pytrader.py)

# === Kiwoom.py === (API 래퍼 클래스)
class Kiwoom(QAxWidget):
    def __init__(self):
        super().__init__()
        self.setControl("KHOPENAPI.KHOpenAPICtrl.1")
        self._set_signal_slots()

    def _set_signal_slots(self):
        self.OnEventConnect.connect(self._event_connect)
        self.OnReceiveTrData.connect(self._receive_tr_data)
        self.OnReceiveChejanData.connect(self._receive_chejan_data)  # 체결잔고

    def send_order(self, rqname, screen_no, acc_no, order_type, code, qty, price, hoga, org_order_no):
        self.dynamicCall("SendOrder(QString,QString,QString,int,QString,int,int,QString,QString)",
                         [rqname, screen_no, acc_no, order_type, code, qty, price, hoga, org_order_no])

# === pytrader.py === (GUI 메인 윈도우)
class MyWindow(QMainWindow, form_class):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.kiwoom = Kiwoom()
        self.kiwoom.comm_connect()  # 로그인

        # 타이머로 주기적 체크
        self.timer = QTimer(self)
        self.timer.start(1000)  # 1초마다
        self.timer.timeout.connect(self.timeout)

    def timeout(self):
        current_time = QTime.currentTime().toString("hh:mm:ss")
        # 장 시작 시간 체크 후 자동 주문 실행
        if current_time == "09:00:00":
            self.auto_trade()

    def auto_trade(self):
        # 매수 대상 종목 리스트 순회하며 주문
        for code in self.buy_list:
            self.kiwoom.send_order("자동매수", "0101", acc_no, 1, code, qty, 0, "03", "")
```

### 실전 활용 포인트
- **프로그램 구조**: Kiwoom.py(API 래퍼) + pytrader.py(GUI/로직) 분리 설계
- **자동 버전 처리**: `pyautogui` 또는 `pywinauto`로 업데이트 팝업 자동 처리
- **윈도우 스케줄러**: `schtasks` 명령 또는 작업 스케줄러 GUI로 매일 장 전 자동 실행
- **체결/잔고 이벤트**: `OnReceiveChejanData`로 주문 체결 실시간 감지
- **SendOrder 파라미터**: 주문유형(1:매수/2:매도), 호가구분("00":지정가/"03":시장가)
- QTimer + QTime으로 장 시간대별 자동 매매 로직 구현

---

## Ch.19 실전 프로그램 개발(2) (개발 5~6일차)

### 핵심 내용
- **종목코드 가져오기**: 유가증권/코스닥 시장 전체 종목 코드 리스트 수집
- **일별 데이터 수집**: 전 종목 일봉 데이터를 연속 조회하여 DB에 저장
- **급등주 포착 알고리즘**: 당일 거래량이 과거 평균 대비 1,000% 이상 급증한 종목 탐지
- **HTML 기초 / 웹 크롤링**: requests + BeautifulSoup으로 웹에서 재무 데이터 수집
- **배당률 기반 투자 알고리즘**: 높은 배당률 종목을 선별하여 투자하는 전략

### 주요 API/코드 패턴

```python
# 종목코드 가져오기
kospi_codes = kiwoom.get_code_list_by_market("0")   # 유가증권
kosdaq_codes = kiwoom.get_code_list_by_market("10")  # 코스닥

# 급등주 포착 알고리즘
def check_speculators(code, ohlcv_df):
    """거래량 급등 종목 판별"""
    avg_volume = ohlcv_df['volume'][1:].mean()  # 과거 평균 거래량 (당일 제외)
    today_volume = ohlcv_df['volume'][0]         # 당일 거래량

    if today_volume > avg_volume * 10:  # 1000% 이상
        return True
    return False

# 웹 크롤링 (배당률 데이터 수집)
import requests
from bs4 import BeautifulSoup

url = "https://finance.naver.com/item/main.nhn?code=005930"
response = requests.get(url)
soup = BeautifulSoup(response.text, 'html.parser')

# 특정 태그에서 배당률 추출
dividend_rate = soup.select_one('.per_table td')

# 배당률 기반 투자 알고리즘
def dividend_strategy(code_list):
    """배당률 상위 종목 선별"""
    result = []
    for code in code_list:
        # 웹 크롤링으로 배당률 수집
        div_rate = get_dividend_rate(code)
        if div_rate and div_rate > 3.0:  # 배당률 3% 이상
            result.append((code, div_rate))

    # 배당률 기준 내림차순 정렬
    result.sort(key=lambda x: x[1], reverse=True)
    return result[:20]  # 상위 20종목
```

### 실전 활용 포인트
- 전 종목 일봉 수집 시 API 호출 제한(초당 횟수) 고려하여 `time.sleep()` 삽입
- 급등주 포착: 단순 거래량 비교 외에도 주가 변동폭, 시가총액 필터 추가 권장
- 웹 크롤링 시 `requests.get(url, headers={'User-Agent': ...})`로 접근 거부 방지
- BeautifulSoup의 `select()`, `select_one()`, `find()`, `find_all()`로 HTML 파싱
- 배당률 기반 전략: 배당락일 전후 주가 변동 고려, 재무 안정성 필터 함께 적용

---

## 실전편 핵심 정리

### 자동매매 시스템 구축 로드맵

```
1단계: 증권사 API 학습 (Ch.10~12)
  └─ 대신증권/이베스트/키움 중 택1 (추천: 키움증권 - 가장 활발한 커뮤니티)
  └─ COM/OCX 기반 API 구조 이해 (SetInput -> Request -> Event -> GetData)

2단계: 데이터 분석 기반 구축 (Ch.13~15)
  └─ Pandas로 주가 데이터 수집/가공
  └─ matplotlib로 차트 시각화
  └─ Zipline으로 전략 백테스팅

3단계: 인프라 구축 (Ch.16~17)
  └─ PyQt GUI로 트레이딩 인터페이스 개발
  └─ SQLite DB로 주가 데이터 영구 저장
  └─ 전 종목 일봉 데이터 수집 파이프라인

4단계: 실전 시스템 통합 (Ch.18~19)
  └─ Kiwoom.py (API 래퍼) + pytrader.py (GUI/로직) 구조
  └─ 자동 로그인 / 버전 처리 / 스케줄러
  └─ 자동 주문 실행 (매수/매도)
  └─ 알고리즘 전략 적용 (급등주/배당률 등)
```

### 공통 아키텍처 패턴

| 구성 요소 | 역할 | 기술 |
|-----------|------|------|
| API 래퍼 | 증권사 API 호출 추상화 | win32com / QAxWidget |
| 데이터 수집 | 주가/재무 데이터 수집 | 증권사 API + 웹크롤링 |
| 데이터 저장 | 수집 데이터 영구 저장 | SQLite + Pandas |
| 데이터 분석 | 전략 개발/백테스팅 | Pandas + Zipline |
| 시각화 | 차트/성과 표시 | matplotlib + mplfinance |
| GUI | 사용자 인터페이스 | PyQt5 + Qt Designer |
| 자동화 | 무인 운영 | 윈도우 스케줄러 + QTimer |

---

## 트레이딩 전략 요약

### 1. 거래량 분석 전략 (Ch.10)
- **원리**: 거래량이 과거 평균 대비 1,000% 이상 급증한 종목을 "대박주" 후보로 선정
- **구현**: 대신증권 StockChart API로 과거 거래량 조회 -> 당일 대비 비율 계산
- **주의**: 거래량 급등이 항상 주가 상승을 의미하지는 않음. 추가 필터 필요

### 2. 업종별 PER 분석 전략 (Ch.10)
- **원리**: 동일 업종 내에서 PER이 상대적으로 낮은 종목 = 저평가 가능성
- **구현**: MarketEye 클래스로 업종 내 전 종목 PER 조회 -> 평균 대비 저PER 종목 선별
- **주의**: PER이 낮은 이유가 실적 악화일 수 있으므로 EPS 추이 함께 확인

### 3. 이동평균선 전략 (Ch.13~14)
- **원리**: 단기 이동평균선이 장기 이동평균선을 상향 돌파(골든크로스)하면 매수, 하향 돌파(데드크로스)하면 매도
- **구현**: Pandas `rolling().mean()`으로 이동평균 계산 -> Zipline으로 백테스팅
- **변형**: 5일/20일, 20일/60일, 5일/20일/60일 다중 이동평균선 전략

### 4. 급등주 포착 알고리즘 (Ch.19)
- **원리**: 거래량이 전일 대비 급증한 종목을 실시간 감지
- **구현**: 키움 API로 전 종목 일봉 조회 -> 거래량 비율 계산 -> 기준 초과 종목 필터링
- **확장**: 주가 상승률, 시가총액, 외국인/기관 수급 조건 추가

### 5. 배당률 기반 투자 전략 (Ch.19)
- **원리**: 배당률이 높은 종목에 투자하여 안정적 수익 추구 (배당주 투자)
- **구현**: 웹 크롤링(requests + BeautifulSoup)으로 배당률 수집 -> 상위 종목 선별
- **주의**: 배당락 후 주가 하락, 배당 지속가능성, 기업 재무 건전성 함께 고려

### 핵심 교훈
- 어떤 전략이든 **백테스팅**을 통한 검증이 필수
- 단일 전략보다 **복합 필터**(거래량 + PER + 이동평균 등)가 효과적
- **리스크 관리**(손절/익절 기준, 포지션 사이징)가 수익률보다 중요
- 실전에서는 **슬리피지, 수수료, API 지연**을 반드시 고려해야 함
