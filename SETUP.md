# ベンチマーク・ナビ セットアップ手順

このアプリを「PC↔スマホで同期」「スマホからも改修できる」状態にするまでの手順です。
所要時間の目安：30〜40分（初回のみ）。全部終われば、以後はURLを開くだけで使えます。

全体の流れ：
1. Firebase でデータの保管先を作る（同期のため）
2. アプリに Firebase のキーを貼る
3. GitHub にコードを置く（スマホから改修できる場所）
4. GitHub Pages で公開する（push＝即反映）

> ⚠️ **本番は GitHub Pages に一本化**。公開URLは
> **https://ohiromerome-hub.github.io/benchmark-navi/**
> （以前あった `*.netlify.app` は古い版なので使わない。混乱の元なので削除推奨）

---

## STEP 1：Firebase をつくる（データの同期先）

1. https://console.firebase.google.com/ に Google でログイン
2. 「プロジェクトを追加」→ 名前は何でもOK（例：benchmark-navi）→ 作成
3. 左メニュー「構築」→「Authentication」→「始める」→「Sign-in method」タブ
   → 「Google」を選び、有効にして保存
4. 左メニュー「構築」→「Firestore Database」→「データベースを作成」
   → 本番環境モードでOK → リージョンは asia-northeast1（東京）推奨
5. 作成後、「ルール」タブを開き、中身を下に置き換えて「公開」：

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{uid} {
      allow read, write: if request.auth != null && request.auth.uid == uid;
    }
    match /public_channels/{doc} {
      allow read: if true;
      allow write: if request.auth != null;
    }
  }
}
```
これで「ログイン本人だけが自分のデータを読み書きできる」状態になります。

`public_channels` はベンチ先チャンネルの公開ミラー（2026-07-14追加）:
ジャンル＆手本で登録した手本の「チャンネル名とURL」だけをアプリが書き込み、
GitHub Actions（tools/sync_channels.py）が無認証で読んでベンチ分析・VPHの
取得対象チャンネル（data/channels.json）へ自動反映します。
個人データ本体（users/…）は従来どおり本人のみアクセス可能です。

### Firebase のキーを取得
6. 左上「プロジェクトの概要」横の歯車 →「プロジェクトの設定」
7. 下にスクロール「マイアプリ」→ `</>`（ウェブ）アイコンをクリック
8. アプリ名を入力して登録 → 表示される `firebaseConfig` の値をコピー
   （apiKey / authDomain / projectId / appId を使います）

---

## STEP 2：アプリにキーを貼る

`benchmark_finder_app.html` をテキストエディタで開き、冒頭近くの
`const firebaseConfig = { ... }` の `PASTE_...` を、STEP1でコピーした値に置き換えます。

```js
const firebaseConfig = {
  apiKey: "ここに実際の値",
  authDomain: "ここに実際の値",
  projectId: "ここに実際の値",
  appId: "ここに実際の値"
};
```

保存したら、ファイルをダブルクリックでブラウザで開いてみてください。
「Googleでログイン」ボタンが出れば成功。ログインして動作確認できます。
（※ ローカルのファイルだとログインのポップアップがブロックされる場合があります。
　その時は STEP4 で公開URLができてから試せば確実です。）

---

## STEP 3：GitHub にコードを置く（スマホから改修できる場所）

1. https://github.com にアカウント作成（無料）
2. 右上「＋」→「New repository」→ 名前を入力（例：benchmark-navi）
   → Public でOK → Create
3. 「uploading an existing file」リンク →
   `benchmark_finder_app.html` を **`index.html` という名前に変えて** アップロード
   （トップページとして開けるようにするためです）
4. Commit changes

これで、スマホの GitHub アプリやブラウザから `index.html` を開いて
直接編集 → コミット、ができるようになります（＝スマホからの改修）。

---

## STEP 4：GitHub Pages で公開する

1. STEP3 のリポジトリ（`ohiromerome-hub/benchmark-navi`）を開く
2. 「Settings」→ 左メニュー「Pages」
3. 「Build and deployment」→ Source =「Deploy from a branch」
4. Branch =「main」/ フォルダ =「/(root)」→「Save」
5. 数十秒〜数分で `https://ohiromerome-hub.github.io/benchmark-navi/` が公開されます

### Firebase 側に公開URLを許可
6. Firebase の「Authentication」→「Settings」→「承認済みドメイン」に
   `ohiromerome-hub.github.io` を追加（これでログインが通ります）

### 自動反映の確認
- 以後、`index.html` を編集して **main に push** すると、
  GitHub Pages が自動で公開サイトを更新します（数十秒〜数分）。
- つまり「コードを直して push → 公開アプリへ反映」。

---

## できあがり

- 公開URL **https://ohiromerome-hub.github.io/benchmark-navi/** を PC・スマホでブックマーク
- 両方で同じ Google アカウントでログイン → データが同期（同じFirebase）
- アプリを直したくなったら、`index.html` を編集して push（スマホ可）

## 改修を私（Claude）に頼むとき
Claude が `index.html` を直して main に push します。GitHub Pages が自動で反映。
（※ 旧 `*.netlify.app` には反映されません。本番は GitHub Pages 一本）

## つまずいたら
- ログインできない → STEP4-6 の「承認済みドメイン（ohiromerome-hub.github.io）」追加を確認
- データが出ない → 同じ Google アカウントでログインしているか確認、STEP1-5 のルール公開を確認
- 画面が真っ白 → STEP2 のキーの貼り間違い（カンマや引用符）を確認
- 古いUIが出る → `*.netlify.app` を開いていないか確認。本番は github.io の方
