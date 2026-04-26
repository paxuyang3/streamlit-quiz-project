import streamlit as st
import pandas as pd
import requests
import os
import matplotlib.pyplot as plt
from matplotlib import font_manager, rc
import glob
import folium
from streamlit_folium import st_folium
import json
import altair as alt

try:
    font_path = "C:/Windows/Fonts/malgun.ttf"
    font = font_manager.FontEntry(fname=font_path, name='MalgunGothic')
    font_manager.fontManager.ttflist.append(font)
    rc('font', family='MalgunGothic')
    plt.rcParams['axes.unicode_minus'] = False
except:
    pass
    
# -----------------------------
# 기본 설정
# -----------------------------
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

st.set_page_config(page_title=" 데이터 활용 대시보드", layout="wide")

# ==========================================
# [추가 조건 1] 앱 첫 화면에 학번과 이름 표시
# ==========================================
st.info("| 학번: 2022204016 | 이름: 유규현 |")

st.title("⚠긴급! 삼성전자 반도체 공장 추가 설치 지역 확인")
st.caption("반도체 공장 어디지역이 적합할까?")

# ==========================================
# [추가 조건 2] 로그인 기능 및 상태 관리
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

# 로그인이 안 되어 있다면 로그인 창을 띄우고, 하단 코드 실행을 중지(st.stop)
if not st.session_state['logged_in']:
    st.write("---")
    st.subheader("삼성전자 시스템 로그인")
    st.write("삼성 내부안건을 확인하고 정보를 풀려면 로그인 인증이 필요합니다.")
    with st.form("login_form"):
        user_id = st.text_input("아이디")
        user_pw = st.text_input("비밀번호", type="password")
        submit_btn = st.form_submit_button("로그인")
        
        if submit_btn:
            if user_id == "2022204016" and user_pw == "samsung4016":
                st.session_state['logged_in'] = True
                st.success("로그인 성공!")
                st.rerun() # 화면 새로고침
            else:
                st.error("아이디 또는 비밀번호가 올바르지 않습니다.")
    st.stop() # ⚠️ 여기서 실행을 멈추어, 로그인을 해야만 아래 원본 코드가 보입니다.

# 로그인 성공 시 우측 상단에 로그아웃 버튼 표시
col_space, col_logout = st.columns([9, 1])
with col_logout:
    if st.button("로그아웃"):
        st.session_state['logged_in'] = False
        st.rerun()

# -----------------------------
# KOSIS API URL
# -----------------------------
KOSIS_URL = (
    "https://kosis.kr/openapi/Param/statisticsParameterData.do?"
    "method=getList"
    "&apiKey=MjQ1ZmU0YzExOWM1ZDQzNjFlMWY0ODk2NjY0NjAxYzU="
    "&itmId=T1+"
    "&objL1=001001+001002+001003+001004+001005+001006+001007+001008+001009+"
    "001010+001011+001012+001013+001014+001015+001016+001017+001019+001021+"
    "001022+001036+001023+001024+001025+001026+001027+001028+001029+001030+"
    "001031+001032+001033+001034+001035+"
    "&objL2=001+"
    "&objL3=T001+"
    "&objL4="
    "&objL5="
    "&objL6="
    "&objL7="
    "&objL8="
    "&format=json"
    "&jsonVD=Y"
    "&prdSe=Y"
    "&startPrdDe=2013"
    "&endPrdDe=2022"
    "&orgId=210"
    "&tblId=DT_21002B015"
)

# -----------------------------
# 1. data 폴더의 CSV 자동 로딩 (캐싱 적용됨)
# -----------------------------
@st.cache_data
def load_all_data():
    csv_list = glob.glob(os.path.join(DATA_DIR, "*.csv"))
    if not csv_list:
        return pd.DataFrame()
    df_list = []

    for f in csv_list:
        loaded = False
        for enc in ["utf-8", "utf-8-sig", "cp949", "euc-kr"]:
            try:
                df = pd.read_csv(f, encoding=enc)
                df_list.append(df)
                loaded = True
                break
            except UnicodeDecodeError:
                continue

        if not loaded:
            st.error(f"❌ 인코딩을 알 수 없어 읽지 못한 파일: {f}")

    if not df_list:
        return pd.DataFrame()

    df_all = pd.concat(df_list, ignore_index=True)
    return df_all

# -----------------------------
# 2. KOSIS API 수집 함수
# -----------------------------
def collect_kosis():
    try:
        st.info("KOSIS API 호출 중입니다...")
        res = requests.get(KOSIS_URL)
        res.raise_for_status()

        json_data = res.json()
        df_raw = pd.DataFrame(json_data)

        # 🔹 1) 필요한 컬럼만 추출: C1_NM(시군명), PRD_DE(년도), DT(합계)
        required_cols = ["C1_NM", "PRD_DE", "DT"]
        missing = [c for c in required_cols if c not in df_raw.columns]
        if missing:
            st.error(f"응답 데이터에 필요한 컬럼이 없습니다: {missing}")
            st.dataframe(df_raw.head())
            return pd.DataFrame(), None

        df_simple = df_raw[required_cols].copy()
        df_simple = df_simple.rename(columns={
            "C1_NM": "시군명",
            "PRD_DE": "년도",
            "DT": "합계"
        })
        df_simple["합계"] = pd.to_numeric(df_simple["합계"], errors="coerce")

        # 🔹 2) 너가 원하는 형태로 피벗:
        #     시군명을 행, 년도를 열, 합계를 값으로
        df_pivot = (
            df_simple
            .pivot_table(index="시군명", columns="년도", values="합계", aggfunc="sum")
            .reset_index()
        )

        # 컬럼명을 2013 → 2013년 이런 식으로 변경
        df_pivot.columns = ["시군명"] + [f"{col}년" for col in df_pivot.columns[1:]]

        # 🔹 3) CSV 저장은 피벗된 형태로
        save_path = os.path.join(
            DATA_DIR,
            "9_경기_시군별_연도별_생산가능인구(외국인).csv"
        )
        df_pivot.to_csv(save_path, index=False, encoding="cp949")

        # 🔹 4) 화면/이후 분석에는 피벗된 형태를 넘겨줌
        return df_pivot, save_path

    except Exception as e:
        st.error(f"KOSIS API 호출 실패: {e}")
        return pd.DataFrame(), None


# -----------------------------
# 3. Streamlit UI 영역
# -----------------------------
st.subheader("📥 데이터 수집 / 불러오기")

col1, col2 = st.columns(2)

with col1:
    if st.button("🛰 경기도 데이터 수집"):
        df_new, path = collect_kosis()
        if not df_new.empty:
            st.success(f"데이터 수집 완료! → 저장 위치: {path}")
            st.dataframe(df_new)
            # 캐시 초기화
            load_all_data.clear()

with col2:
    if st.button("🔄전체 데이터 다시 불러오기"):
        st.info("새로운 데이터를 포함하여 전체 파일을 다시 불러옵니다.")
        load_all_data.clear()

# -----------------------------
# 4. 누적 데이터 출력
# -----------------------------
st.subheader("📊전체 데이터")

df_all = load_all_data()
if df_all.empty:
    st.warning("아직 data 폴더에 CSV 파일이 없습니다.")
else:
    st.dataframe(df_all)
    
st.write("---")
st.subheader("🗑 데이터 삭제 기능")

# data 폴더 내 CSV 목록 가져오기
csv_list = glob.glob(os.path.join(DATA_DIR, "*.csv"))

if not csv_list:
    st.info("삭제할 CSV 파일이 없습니다.")
else:
    # 파일명만 리스트로 변환
    file_names = [os.path.basename(f) for f in csv_list]

    # 멀티 선택
    files_to_delete = st.multiselect(
        "삭제할 파일을 선택하세요.",
        options=file_names)

    if files_to_delete:
        st.warning(f"선택한 파일을 삭제하기:{files_to_delete}")

        if st.button("선택 파일 삭제하기"):
            for fname in files_to_delete:
                fpath = os.path.join(DATA_DIR, fname)
                try:
                    os.remove(fpath)
                except Exception as e:
                    st.error(f"{fname} 삭제 실패: {e}")

            st.success("선택한 파일이 삭제되었습니다.")

            
# -----------------------------
# 5. 추가 분석 자리
# -----------------------------
st.write("---")
st.subheader("📈시각화 영역")

st.write("👉 그래프 시각화")
df_all = load_all_data()

if df_all.empty:
    st.info("위에서 먼저 데이터를 수집하거나 data 폴더에 CSV를 넣어 주세요.")
else:
    # 1) 시각화용 데이터 정리 (중복 시군이 있다면 합계)
    #    → 시군명, 2013년~2022년 컬럼만 사용
    year_cols = [c for c in df_all.columns if c.endswith("년")]
    if "시군명" not in df_all.columns or not year_cols:
        st.error("⚠️ '시군명' 또는 'YYYY년' 형태의 연도 컬럼을 찾을 수 없습니다.")
    else:
        df_viz = df_all[["시군명"] + year_cols].copy()
        df_viz = df_viz.groupby("시군명", as_index=False)[year_cols].sum()

        # -------------------------
        # 5-1) 시군별 연도 추이 (라인차트)
        # -------------------------
        st.markdown("### 시군별_연도별_생산가능인구수 추이")

        regions = st.multiselect(
            "시군을 선택하세요.",
            options=df_viz["시군명"].unique().tolist(),
            default=df_viz["시군명"].unique().tolist()[1:3] 
        )

        if regions:
            df_sel = df_viz[df_viz["시군명"].isin(regions)].copy()

            # wide → long (년도/합계 형태로 변환)
            df_long = df_sel.melt(
                id_vars="시군명",
                value_vars=year_cols,
                var_name="년도",
                value_name="합계"
            )
            # "2013년" → 2013
            df_long["년도"] = df_long["년도"].str.replace("년", "", regex=False).astype(int)

            import altair as alt

            line_chart = (
                alt.Chart(df_long)
                .mark_line(point=True)
                .encode(
                    x="년도:O",
                    y="합계:Q",
                    color="시군명:N",
                    tooltip=["시군명", "년도", "합계"]
                )
                .properties(height=400)
            )
            st.altair_chart(line_chart, use_container_width=True)
        else:
            st.info("시각화할 시군을 하나 이상 선택하세요.")

        # -------------------------
        # 5-2) 시군 × 연도 Heatmap
        # -------------------------
        st.markdown("### heatmap")

        # heatmap용 long 데이터
df_all = load_all_data()

if df_all.empty:
    st.warning("data 폴더에 불러온 데이터가 없습니다. (히트맵 생성 불가)")
else:
    if "시군명" not in df_all.columns:
        st.error("'시군명' 컬럼을 찾을 수 없습니다. 히트맵용 CSV에 '시군명' 컬럼이 있어야 합니다.")
    else:
        # 1) 연도 컬럼 자동 탐색 (예: 2013년, 2014년, ...)
        year_cols = [c for c in df_all.columns if c.endswith("년")]

        if not year_cols:
            st.error("'XXXX년' 형식의 연도 컬럼을 찾지 못했습니다.")
        else:
            # 숫자형으로 변환
            df_num = df_all.copy()
            for col in year_cols:
                df_num[col] = pd.to_numeric(df_num[col], errors="coerce")

            # 2) 시군 선택 박스 (선택 안 하면 전체)
            all_sigung = sorted(df_num["시군명"].dropna().unique().tolist())
            default_selection = all_sigung[1:3]  

            selected_sigung = st.multiselect(
                "📌 히트맵에 표시할 시군을 선택하세요",
                options=all_sigung,
                default=default_selection,
            )

            if selected_sigung:
                df_heat = df_num[df_num["시군명"].isin(selected_sigung)]
            else:
                df_heat = df_num

            # 3) 시군 × 연도 행렬 만들기 (시군별 합계)
            heat_data = (
                df_heat
                .groupby("시군명", as_index=True)[year_cols]
                .sum(numeric_only=True)
            )

            if heat_data.empty:
                st.warning("선택한 시군에 해당하는 데이터가 없습니다.")
            else:
                # 4) 히트맵 그리기
                n_rows = len(heat_data)
                fig_height = max(4, 0.35 * n_rows)  # 시군 개수에 따라 자동으로 세로 크기 키우기

                fig, ax = plt.subplots(figsize=(12, fig_height))

                im = ax.imshow(
                    heat_data.values,
                    aspect="auto",
                    cmap="Blues",
                    origin="upper"
                )

                # x축: 연도
                ax.set_xticks(range(len(year_cols)))
                ax.set_xticklabels(
                    [c.replace("년", "") for c in year_cols],
                    rotation=45,
                    ha="right"
                )

                # y축: 시군명
                ax.set_yticks(range(len(heat_data.index)))
                ax.set_yticklabels(heat_data.index)

                ax.set_xlabel("연도")
                ax.set_ylabel("시군명")
                ax.set_title("Heatmap", pad=15)

                cbar = fig.colorbar(im, ax=ax)
                cbar.set_label("합계")

                st.pyplot(fig)
                

st.write("---")
st.subheader("🗺 전국 시군별 지도 시각화")

# GeoJSON 파일 자동 로드
GEOJSON_PATH = "data/skorea_municipalities_geo_simple.json"  # 전국 GeoJSON

if not os.path.exists(GEOJSON_PATH):
    st.error("지도 GeoJSON 파일이 존재하지 않습니다.")
else:
    with open(GEOJSON_PATH, encoding="utf-8") as f:
        geo_data = json.load(f)

    # data 폴더에서 읽어온 전체 데이터
    df_all = load_all_data()

    if df_all.empty:
        st.warning("data 폴더에서 불러온 CSV 데이터가 없습니다.")
    elif "시군명" not in df_all.columns:
        st.error("'시군명' 컬럼을 찾을 수 없습니다. CSV 형식을 확인해주세요.")
    else:
        # 1) 연도 컬럼 자동 탐색 (예: 2013년, 2014년, ...)
        year_cols = [c for c in df_all.columns if c.endswith("년")]
        if not year_cols:
            st.error("'XXXX년' 형식의 연도 컬럼이 없습니다.")
        else:
            # 같은 시군명 여러 개면 먼저 합쳐주기
            df_viz = df_all[["시군명"] + year_cols].groupby("시군명", as_index=False).sum(numeric_only=True)

            # 2) 지도에 표시할 연도 선택
            선택연도 = st.selectbox("지도에 표시할 연도를 선택하세요.", year_cols)
            df_map = df_viz[["시군명", 선택연도]].copy()
            df_map = df_map.rename(columns={선택연도: "값"})
            df_map["값"] = pd.to_numeric(df_map["값"], errors="coerce")

            st.write(f"### {선택연도} 기준 시군별 값")
            st.dataframe(df_map)

            # 3) GeoJSON 안 시군명 목록 (properties["name"] 기준)
            geo_names = [feat["properties"]["name"] for feat in geo_data["features"]]

            # --- 이름 정규화 함수 (공백/괄호 제거) ---
            import re

            def normalize(s: str) -> str:
                if s is None:
                    return ""
                s = str(s)
                s = s.replace(" ", "")
                s = re.sub(r"\(.*?\)", "", s)  # 괄호 내용 제거
                return s

            geo_norm_list = [(g, normalize(g)) for g in geo_names]

            # ---  CSV 시군명 → 매칭되는 GeoJSON name "여러 개" 찾기 ---
            def map_to_geo_names(x: str):
                nx = normalize(x)
                if not nx:
                    return []
                # 1) 정규화 이름이 포함된 모든 GeoJSON name 가져오기
                matches = [orig for (orig, gnorm) in geo_norm_list if nx in gnorm or gnorm in nx]
                return matches

            # 4) CSV 시군명마다 매칭되는 GeoJSON name 리스트 만들기
            df_map["geo_names"] = df_map["시군명"].apply(map_to_geo_names)

            # 매칭 안 된 것 체크
            unmatched = df_map[df_map["geo_names"].apply(len) == 0]["시군명"].unique()
            if len(unmatched) > 0:
                st.warning(f"GeoJSON과 매칭되지 않은 시군명: {list(unmatched)}")

            # 5) 매칭된 GeoJSON name별로
            df_expanded = df_map.explode("geo_names").dropna(subset=["geo_names"]).copy()
            df_expanded = df_expanded.rename(columns={"geo_names": "geo_name"})

            # 6) folium 지도 생성
            m = folium.Map(location=[36.5, 127.8], zoom_start=7, tiles="cartodbpositron")

            # Choropleth: GeoJSON properties['name'] 기준으로 조인
            choropleth = folium.Choropleth(
                geo_data=geo_data,
                data=df_expanded,
                columns=["geo_name", "값"],
                key_on="feature.properties.name",  # GeoJSON 속성: name
                fill_color="YlOrRd",
                fill_opacity=0.8,
                line_opacity=0.5,
                nan_fill_color="lightgrey",
                legend_name=f"{선택연도} 값",
            ).add_to(m)

            # Tooltip (시군명 표시)
            folium.GeoJsonTooltip(
                fields=["name"],
                aliases=["시군명:"],
                localize=True,
                sticky=True
            ).add_to(choropleth.geojson)

            st_folium(m, width=900, height=600)

st.write("---")
st.markdown("### 연도별 생산가능 인구 수 Top N 도시")

# (year_cols 변수가 위쪽 스코프에서 정의되었는지 확인하기 위한 예외처리)
try:
    year_cols
except NameError:
    year_cols = []

if year_cols:  # year_cols는 이미 위에서 만든 리스트
    # 연도 선택 (예: 2013년~2022년 중 선택)
    year_options = sorted(year_cols)  # ['2013년', '2014년', ...]
    선택연도_topn = st.selectbox(
        "Top N 도시를 볼 연도를 선택하세요.",
        options=year_options,
        index=len(year_options) - 1  # 기본값: 마지막 연도(예: 2022년)
    )

    # 시군 개수에 맞춰 Top N 슬라이더 설정
    try:
        max_n = min(10, len(df_viz))  # 최대 10개까지
    except NameError:
        max_n = 10
        
    top_n = st.slider(
        "Top N 개수 선택",
        min_value=1,
        max_value=max_n,
        value=min(5, max_n)  # 기본 5개 (데이터가 더 적으면 자동 조정)
    )

    # 선택한 연도 기준 Top N 시군 추출
    if 'df_viz' in locals():
        df_latest = (
            df_viz[["시군명", 선택연도_topn]]
            .sort_values(선택연도_topn, ascending=False)
            .head(top_n)
        )

        st.write(f"**{선택연도_topn} 기준 Top {top_n} 시군**")
        st.dataframe(df_latest)

        import altair as alt
        bar_chart = (
            alt.Chart(df_latest)
            .mark_bar()
            .encode(
                x=alt.X(f"{선택연도_topn}:Q", title=선택연도_topn),
                y=alt.Y("시군명:N", sort="-x", title="시군명"),
                tooltip=["시군명", 선택연도_topn]
            )
            .properties(height=400)
        )
        st.altair_chart(bar_chart, use_container_width=True)

# -------------------------------------
# 6. data/data2 폴더 – 제조업 비율 계산
# -------------------------------------
st.write("---")
st.subheader("🏭 추천 도시 제조업 비율 비교")

DATA2_DIR = os.path.join("data", "data2")

# (캐싱 적용됨)
@st.cache_data
def load_industry_share():
    csv_list = glob.glob(os.path.join(DATA2_DIR, "*.csv"))
    if not csv_list:
        return pd.DataFrame()

    rows = []

    for path in csv_list:
        fname = os.path.basename(path)
        try:
            df = pd.read_csv(path, encoding="cp949")
        except UnicodeDecodeError:
            df = pd.read_csv(path, encoding="utf-8-sig")

        city_col = df.columns[0]
        city_name = city_col

        df_idx = df.set_index(city_col)

        if "합계" not in df_idx.index or "제조업" not in df_idx.index:
            st.warning(f"⚠️ {fname} 파일에서 '합계' 또는 '제조업' 행을 찾지 못했습니다.")
            continue

        year_cols = [c for c in df.columns if c != city_col]
        df_idx[year_cols] = df_idx[year_cols].apply(pd.to_numeric, errors="coerce")

        total = df_idx.loc["합계", year_cols].astype(float)
        manu  = df_idx.loc["제조업", year_cols].astype(float)
        share = (manu / total * 100.0)

        for year in year_cols:
            rows.append({
                "도시": city_name,
                "연도": int(year),
                "합계": total[year],
                "제조업": manu[year],
                "제조업비율(%)": share[year]
            })

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)

df_share = load_industry_share()

if df_share.empty:
    st.info("data/data2 폴더에 읽을 수 있는 제조업 csv 파일이 없습니다.")
else:

    # ----------------------------
    # 선택한 연도 기준 Top N 도시
    # ----------------------------
    st.markdown("#### 🏆 연도 기준 추천 도시 제조업 비율")

    year_options = sorted(df_share["연도"].unique().tolist())
    selected_year = st.selectbox("연도를 선택하세요.", options=year_options, index=len(year_options) - 1)

    city_options = sorted(df_share["도시"].unique().tolist())

    df_year = df_share[df_share["연도"] == selected_year].copy()
    df_year = df_year.sort_values("제조업비율(%)", ascending=False)
    st.write(f"**{selected_year}년 추천도시 제조업 비율**")
    st.dataframe(df_year)

    bar_chart = (
        alt.Chart(df_year)
        .mark_bar()
        .encode(
            x=alt.X("제조업비율(%):Q", title="제조업 비율(%)"),
            y=alt.Y("도시:N", sort="-x", title="도시"),
            color=alt.condition(
            alt.FieldEqualPredicate(field='도시', equal='김해시'),
            alt.value('#d9534f'),     # 김해시 색상 강조
            alt.value('#6c757d')
            ),
            tooltip=["도시", "연도", "제조업비율(%)", "합계", "제조업"]
        )
        .properties(height=400)
    )
    st.altair_chart(bar_chart, use_container_width=True)

# ==========================================
# 간단한 퀴즈
# ==========================================
st.write("---")
st.subheader("💡 내용 확인 인증용 퀴즈(설문조사)")
st.write("본 내용을 확인했는지에 대한 검증용 퀴즈입니다.")

st.write("---")
st.subheader("📝 응시자 정보")

# 폼을 사용하여 학번과 이름을 한 번에 제출받습니다.
with st.form("user_info_form"):
    # 정답을 비교하지 않고 단순히 입력만 받는 text_input
    samsung_id = st.text_input("사번을 입력하세요.")
    samsung_name = st.text_input("이름을 입력하세요.")
    
    # 채점이 아닌 단순 제출 버튼
    submit_info = st.form_submit_button("정보 확인")
    
    if submit_info:
        # 두 칸이 모두 채워졌는지 확인 (빈칸 방지)
        if samsung_id and samsung_name:
            st.success(f"반갑습니다! {samsung_id} {samsung_name}님.")
            
            # (선택 사항) 입력받은 정보를 session_state에 저장하여 
            # 다른 페이지나 퀴즈 결과창에서 활용할 수 있습니다.
            st.session_state['current_samsung_id'] = samsung_id
            st.session_state['current_samsung_name'] = samsung_name
        else:
            # 빈칸이 있을 경우 경고 메시지 출력
            st.warning("사번과 이름을 모두 입력해 주세요.")

with st.form("dashboard_quiz"):
    q1 = st.radio(
        "Q1. 이 대시보드에서 공장 부지 선정 기준으로 활용한 두 가지 핵심 데이터는 무엇인가요?",
        ["수도권 접근성과 세금 혜택", "제조업 비율과 생산가능인구", "평균 기온과 강수량"],
        index=None
    )
    
    q2 = st.radio(
        "Q2. 2022년 기준 가장 제조업 비율이 높은 도시는 어디입니까?",
        ["김해시", "아산시", "구미시", "천안시", "청주시"],
        index=None
    )

    q3 = st.text_input("Q3. 반도체 공장 부지 선점을 위해 인력 확보 측면에서 살펴본 인구 지표는 'OOOO인구' 입니다. 빈칸에 알맞은 단어는?")

    q4 = st.text_input("Q4. 이 데이터는 2013년부터 몇년간의 데이터를 설명하고 있나요?")
    
    q5 = st.radio(
        "Q5. 2022년 기준 김해시는 생산가능 인구수 top5에 들어간다.",
        ["O", "X"],
        index=None
    )
    submit_quiz = st.form_submit_button("정답 제출")
    
    if submit_quiz:
        score = 0
        if q1 == "제조업 비율과 생산가능인구":
            score += 20
        if q2 == "김해시":
            score += 20
        if q3.replace(" ", "") == "생산가능":
            score += 20
        if q4.strip().lower() == "10":
            score += 20
        if q5 == "O":
            score += 20
            
        st.success(f"퀴즈에 응해주셔서 감사합니다! 총 100점 만점에 **{score}점** 입니다.")
        if score == 100:
            st.balloons()
