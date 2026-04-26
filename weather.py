import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# --- 1. 設定・緯度経度辞書 ---
LOCATION_COORDS = {
    "長島": {"lat": 32.188, "lon": 130.141},
    "西之表": {"lat": 30.733, "lon": 131.000},
    "中種子": {"lat": 30.550, "lon": 130.950},
    "南種子": {"lat": 30.383, "lon": 130.866},
    "指宿": {"lat": 31.233, "lon": 130.633},
    "農業開発総合センター熊毛支場": {"lat": 30.702, "lon": 130.981}
}

file_name = "normals_daily.csv"
ALIGN_YEAR = 2024  # グラフのX軸（うるう年対応）を揃える基準年

# --- 2. データ読み込み（CSVの平年値） ---
@st.cache_data
def load_normal_data_csv():
    try:
        df = pd.read_csv(file_name, encoding="shift-jis")
    except (FileNotFoundError, UnicodeDecodeError):
        try:
            df = pd.read_csv(file_name, encoding="utf-8")
        except:
            st.warning(f"⚠️ `{file_name}` が見つかりません。CSVの平年値は利用できません。")
            return pd.DataFrame()
            
    temp_date = pd.to_datetime(df["日付"], errors="coerce")
    df["日付"] = pd.to_datetime(f"{ALIGN_YEAR}-" + temp_date.dt.strftime('%m-%d'), errors="coerce")
    
    # CSVに降水量の平年値がない場合は0を入れておく
    if "平年降水量" not in df.columns:
        df["平年降水量"] = 0
    return df.dropna(subset=['日付'])

# --- 3. Open-Meteo Archive APIから過去10年間の平均値を算出 ---
@st.cache_data(ttl="7d")
def fetch_10yr_normal_data():
    now = datetime.now()
    # 前年を基準に過去10年間のデータを取得
    end_year = now.year - 1
    start_year = end_year - 9
    start_date = f"{start_year}-01-01"
    end_date = f"{end_year}-12-31"

    lats = ",".join([str(v["lat"]) for v in LOCATION_COORDS.values()])
    lons = ",".join([str(v["lon"]) for v in LOCATION_COORDS.values()])
    
    url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lats}&longitude={lons}&start_date={start_date}&end_date={end_date}&daily=temperature_2m_mean,precipitation_sum&timezone=Asia%2FTokyo"
    
    response = requests.get(url)
    if response.status_code != 200:
        st.error("⚠️ 過去10年分の気象データ取得に失敗しました。")
        return pd.DataFrame()
        
    data = response.json()
    loc_names = list(LOCATION_COORDS.keys())
    result_list = []
    
    for i, loc in enumerate(loc_names):
        loc_data = data[i] if isinstance(data, list) else data
        df = pd.DataFrame({
            "フル日付": pd.to_datetime(loc_data["daily"]["time"]),
            "気温": loc_data["daily"]["temperature_2m_mean"],
            "降水量": loc_data["daily"]["precipitation_sum"]
        })
        df = df.dropna()
        df["月日"] = df["フル日付"].dt.strftime('%m-%d')
        
        # 月日でグループ化して10年間の平均を算出
        df_mean = df.groupby("月日")[["気温", "降水量"]].mean().reset_index()
        df_mean["地点"] = loc
        df_mean["日付"] = pd.to_datetime(f"{ALIGN_YEAR}-" + df_mean["月日"], errors="coerce")
        df_mean = df_mean.rename(columns={"気温": "平年気温", "降水量": "平年降水量"})
        result_list.append(df_mean)
        
    return pd.concat(result_list, ignore_index=True)

# --- 4. Open-Meteo APIから指定した年のデータを一括取得 ---
@st.cache_data(ttl="1d")
def fetch_weather_data_by_year(target_year):
    now = datetime.now()
    current_year = now.year
    
    start_date = f"{target_year}-01-01"
    
    # 🌟 修正箇所：今年の場合はAPIの遅延を考慮して「7日前」までを取得する
    if target_year == current_year:
        end_date = (now - timedelta(days=7)).strftime('%Y-%m-%d')
    else:
        end_date = f"{target_year}-12-31"
    
    lats = ",".join([str(v["lat"]) for v in LOCATION_COORDS.values()])
    lons = ",".join([str(v["lon"]) for v in LOCATION_COORDS.values()])
    
    url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lats}&longitude={lons}&start_date={start_date}&end_date={end_date}&daily=temperature_2m_mean,precipitation_sum&timezone=Asia%2FTokyo"
    
    response = requests.get(url)
    if response.status_code != 200:
        st.error(f"⚠️ {target_year}年の気象データ取得に失敗しました。")
        return {}
        
    data = response.json()
    loc_names = list(LOCATION_COORDS.keys())
    result_dict = {}
    
    for i, loc in enumerate(loc_names):
        loc_data = data[i] if isinstance(data, list) else data
        df = pd.DataFrame({
            "フル日付": pd.to_datetime(loc_data["daily"]["time"]),
            "気温": loc_data["daily"]["temperature_2m_mean"],
            "降水量": loc_data["daily"]["precipitation_sum"]
        })
        
        # 🌟 修正箇所：気温データが空（null）の日付も削除してグラフ描画エラーを防ぐ
        df = df.dropna(subset=["フル日付", "気温"])
        
        df["日付"] = pd.to_datetime(f"{ALIGN_YEAR}-" + df["フル日付"].dt.strftime('%m-%d'), errors="coerce")
        result_dict[loc] = df
        
    return result_dict

# --- 5. 画面レイアウト ---
st.set_page_config(page_title="鹿児島気象ダッシュボード", layout="wide")
st.title("🌡️ 鹿児島6地点 気温・降水量ダッシュボード")

# 平年値データの読み込み
df_normal_csv = load_normal_data_csv()
with st.spinner("過去10年間の平均データを構築しています..."):
    df_normal_api = fetch_10yr_normal_data()

# サイドバー設定
current_year = datetime.now().year
st.sidebar.header("⚙️ データ設定")

years_options = [current_year, current_year-1, current_year-2, current_year-3]
selected_year = st.sidebar.selectbox("表示・比較する年を選択", years_options, index=0)

normal_type = st.sidebar.radio(
    "基準とする平年値のデータ元", 
    ["過去10年平均 (Open-Meteo Archive)", "気象庁平年値 (CSVファイル)"]
)

# 選択された平年値データをセット
if normal_type == "気象庁平年値 (CSVファイル)" and not df_normal_csv.empty:
    df_normal = df_normal_csv
else:
    df_normal = df_normal_api

with st.spinner(f"{selected_year}年のデータを取得しています..."):
    weather_data_dict = fetch_weather_data_by_year(selected_year)

st.sidebar.subheader("📅 表示期間")
s_date = st.sidebar.date_input("開始日", value=datetime(selected_year, 1, 1))
e_date = st.sidebar.date_input("終了日", value=datetime(selected_year, 12, 31))
show_precip = st.sidebar.checkbox("降水量を表示する", value=True)

start_dt = pd.to_datetime(f"{ALIGN_YEAR}-{s_date.strftime('%m-%d')}")
end_dt = pd.to_datetime(f"{ALIGN_YEAR}-{e_date.strftime('%m-%d')}")

mode = st.radio("分析モード", ["平年値と選択した年の比較", "2地点間の比較"])

def filter_data(loc_name, start, end):
    n_data = pd.DataFrame()
    if not df_normal.empty:
        n_data = df_normal[(df_normal["地点"] == loc_name) & (df_normal["日付"] >= start) & (df_normal["日付"] <= end)]
    
    c_data = pd.DataFrame()
    if loc_name in weather_data_dict:
        c_df = weather_data_dict[loc_name]
        c_data = c_df[(c_df["日付"] >= start) & (c_df["日付"] <= end)]
    return n_data, c_data

# --- 6. グラフ描画 ---
if mode == "平年値と選択した年の比較":
    target = st.selectbox("地点を選択", list(LOCATION_COORDS.keys()))
    n_data, c_data = filter_data(target, start_dt, end_dt)
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # 平年値の描画
    if not n_data.empty:
        fig.add_trace(go.Scatter(x=n_data["日付"], y=n_data["平年気温"], name="平年気温", line=dict(dash='dot', color='gray')), secondary_y=False)
        if show_precip and "平年降水量" in n_data.columns:
            fig.add_trace(go.Scatter(x=n_data["日付"], y=n_data["平年降水量"], name="平年降水量", line=dict(dash='dot', color='lightblue', width=2), fill='tozeroy'), secondary_y=True)
    
    # 選択年の描画
    if not c_data.empty:
        fig.add_trace(go.Scatter(x=c_data["日付"], y=c_data["気温"], name=f"{selected_year}年の気温", line=dict(color='blue', width=2)), secondary_y=False)
        if show_precip:
            fig.add_trace(go.Bar(x=c_data["日付"], y=c_data["降水量"], name=f"{selected_year}年の降水量", marker_color='rgba(0, 0, 255, 0.3)'), secondary_y=True)

    fig.update_layout(title=f"{target}の推移 ({selected_year}年)", hovermode="x unified")
    fig.update_yaxes(title_text="気温 (℃)", secondary_y=False)
    fig.update_yaxes(title_text="降水量 (mm)", secondary_y=True, showgrid=False)
    fig.update_xaxes(tickformat="%m/%d")
    st.plotly_chart(fig, use_container_width=True)

elif mode == "2地点間の比較":
    col1, col2 = st.columns(2)
    with col1: loc1 = st.selectbox("地点1", list(LOCATION_COORDS.keys()), index=1)
    with col2: loc2 = st.selectbox("地点2", list(LOCATION_COORDS.keys()), index=5)
    
    n1, c1 = filter_data(loc1, start_dt, end_dt)
    n2, c2 = filter_data(loc2, start_dt, end_dt)
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # 地点1の描画
    if not n1.empty:
        fig.add_trace(go.Scatter(x=n1["日付"], y=n1["平年気温"], name=f"{loc1} (平年気温)", line=dict(dash='dot', color='royalblue')), secondary_y=False)
        if show_precip and "平年降水量" in n1.columns:
            fig.add_trace(go.Scatter(x=n1["日付"], y=n1["平年降水量"], name=f"{loc1} (平年降水)", line=dict(dash='dot', color='rgba(65, 105, 225, 0.5)')), secondary_y=True)
            
    if not c1.empty:
        fig.add_trace(go.Scatter(x=c1["日付"], y=c1["気温"], name=f"{loc1} ({selected_year}年気温)", line=dict(color='blue', width=2)), secondary_y=False)
        if show_precip:
            fig.add_trace(go.Bar(x=c1["日付"], y=c1["降水量"], name=f"{loc1} ({selected_year}年降水)", marker_color='rgba(65, 105, 225, 0.3)'), secondary_y=True)
            
    # 地点2の描画
    if not n2.empty:
        fig.add_trace(go.Scatter(x=n2["日付"], y=n2["平年気温"], name=f"{loc2} (平年気温)", line=dict(dash='dot', color='indianred')), secondary_y=False)
        if show_precip and "平年降水量" in n2.columns:
             fig.add_trace(go.Scatter(x=n2["日付"], y=n2["平年降水量"], name=f"{loc2} (平年降水)", line=dict(dash='dot', color='rgba(255, 0, 0, 0.5)')), secondary_y=True)
             
    if not c2.empty:
        fig.add_trace(go.Scatter(x=c2["日付"], y=c2["気温"], name=f"{loc2} ({selected_year}年気温)", line=dict(color='red', width=2)), secondary_y=False)
        if show_precip:
            fig.add_trace(go.Bar(x=c2["日付"], y=c2["降水量"], name=f"{loc2} ({selected_year}年降水)", marker_color='rgba(255, 0, 0, 0.3)'), secondary_y=True)

    fig.update_layout(title=f"{loc1} vs {loc2} 比較 ({selected_year}年)", barmode='group', hovermode="x unified")
    fig.update_yaxes(title_text="気温 (℃)", secondary_y=False)
    fig.update_yaxes(title_text="降水量 (mm)", secondary_y=True, showgrid=False)
    fig.update_xaxes(tickformat="%m/%d")
    st.plotly_chart(fig, use_container_width=True)
# --- 7. データダウンロード機能 (コードの最後に追加) ---
st.sidebar.markdown("---")
st.sidebar.subheader("📥 データのダウンロード")

def convert_df_to_csv(df):
    # Excelでの文字化け防止のため utf-8-sig を使用
    return df.to_csv(index=False).encode('utf_8_sig')

if mode == "平年値と選択した年の比較":
    if not c_data.empty:
        # ダウンロード用にデータを整理
        # 平年値データがある場合は結合して表示
        if not n_data.empty:
            dl_df = pd.merge(
                n_data[['日付', '平年気温', '平年降水量']], 
                c_data[['日付', '気温', '降水量']], 
                on='日付', how='outer'
            ).rename(columns={'気温': f'{selected_year}年気温', '降水量': f'{selected_year}年降水量'})
        else:
            dl_df = c_data.copy()
            
        # 日付を見やすく整形（元の2024年設定から月日のみに）
        dl_df['日付'] = dl_df['日付'].dt.strftime('%m-%d')
        
        csv_data = convert_df_to_csv(dl_df)
        st.sidebar.download_button(
            label=f"📊 {target}のデータをCSV保存",
            data=csv_data,
            file_name=f"weather_data_{target}_{selected_year}.csv",
            mime='text/csv',
        )

elif mode == "2地点間の比較":
    # 2地点のデータを結合
    try:
        # 地点1
        d1 = c1[['日付', '気温', '降水量']].copy()
        d1.columns = ['日付', f'{loc1}_気温', f'{loc1}_降水量']
        # 地点2
        d2 = c2[['日付', '気温', '降水量']].copy()
        d2.columns = ['日付', f'{loc2}_気温', f'{loc2}_降水量']
        
        dl_df_comp = pd.merge(d1, d2, on='日付', how='outer')
        dl_df_comp['日付'] = dl_df_comp['日付'].dt.strftime('%m-%d')
        
        csv_data_comp = convert_df_to_csv(dl_df_comp)
        st.sidebar.download_button(
            label=f"📊 2地点比較データをCSV保存",
            data=csv_data_comp,
            file_name=f"comparison_{loc1}_vs_{loc2}_{selected_year}.csv",
            mime='text/csv',
        )
    except Exception as e:
        st.sidebar.info("データ準備中...")
