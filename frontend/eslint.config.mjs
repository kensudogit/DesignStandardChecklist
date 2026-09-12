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
       * 現状8件該当し、いずれもマウント時のデータ取得
       * (`useEffect(() => { void load() }, [load])`) である。動作しているコードを
       * 8ファイル同時に書き換えるのはこの MR の範囲を超えるため、警告に留める。
       *
       * package.json の lint スクリプトで --max-warnings 8 を指定してあるので、
       * 9件目が入ると CI が落ちる。今ある分は残るが、増えはしない。
       * 解消は別 Issue で1ファイルずつ行う。
       */
      "react-hooks/set-state-in-effect": "warn",
    },
  },
];

export default config;
