import next from "eslint-config-next";
import typescript from "eslint-config-next/typescript";

/**
 * Next.js 16 で `next lint` が廃止されたため、ESLint を直接呼ぶ flat config。
 *
 * 方針: 導入時点で緑に回る設定から始める。既存コードに大量の指摘が出る状態で
 * 必須化すると、全員がこの検査を無視するようになり、以後どんな指摘も届かなくなる。
 */
const config = [
  { ignores: [".next/**", "node_modules/**", "next-env.d.ts"] },
  ...next,
  ...typescript,
  {
    rules: {
      /**
       * useEffect の中から setState を同期的に呼ぶと再レンダリングが連鎖する、という指摘。
       *
       * 残り6件はいずれもマウント時のデータ取得
       * (`useEffect(() => { void load() }, [load])`) である。setState は await の
       * 後に走るため同期的な再レンダリングの連鎖ではなく、規則が async を
       * 追えていない面が強い。動作しているコードを書き換える利得が小さいので
       * 警告に留める。
       *
       * 一方、props の変化で state をリセットしていた2件は実害があったため
       * 描画中の調整へ直した (ChecklistTable / ConsolidatedTable)。
       *
       * package.json の lint スクリプトで --max-warnings 6 を指定してあるので、
       * 7件目が入ると CI が落ちる。今ある分は残るが、増えはしない。
       */
      "react-hooks/set-state-in-effect": "warn",
    },
  },
];

export default config;
