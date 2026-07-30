<!-- prose-lint: off -->
<!-- A URL catalog. The prose rules do not apply to badge markup. -->

# Badge catalog

Copy these rather than rebuilding them. Logo slugs and hex colors are easy to get subtly wrong, and a wrong slug renders a blank badge that looks fine in the diff.

All use `style=for-the-badge`. Check the first one renders when you add a badge you have not used before.

## Languages

```
https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54
https://img.shields.io/badge/typescript-%23007ACC.svg?style=for-the-badge&logo=typescript&logoColor=white
https://img.shields.io/badge/javascript-%23323330.svg?style=for-the-badge&logo=javascript&logoColor=%23F7DF1E
https://img.shields.io/badge/rust-%23000000.svg?style=for-the-badge&logo=rust&logoColor=white
https://img.shields.io/badge/go-%2300ADD8.svg?style=for-the-badge&logo=go&logoColor=white
https://img.shields.io/badge/latex-%23008080.svg?style=for-the-badge&logo=latex&logoColor=white
https://img.shields.io/badge/SQL-%23025E8C.svg?style=for-the-badge&logo=amazon-dynamodb&logoColor=white
```

## AI and ML

```
https://img.shields.io/badge/PyTorch-%23EE4C2C.svg?style=for-the-badge&logo=PyTorch&logoColor=white
https://img.shields.io/badge/TensorFlow-%23FF6F00.svg?style=for-the-badge&logo=TensorFlow&logoColor=white
https://img.shields.io/badge/scikit--learn-%23F7931E.svg?style=for-the-badge&logo=scikit-learn&logoColor=white
https://img.shields.io/badge/numpy-%23013243.svg?style=for-the-badge&logo=numpy&logoColor=white
https://img.shields.io/badge/pandas-%23150458.svg?style=for-the-badge&logo=pandas&logoColor=white
https://img.shields.io/badge/SciPy-%230C55A5.svg?style=for-the-badge&logo=scipy&logoColor=white
https://img.shields.io/badge/Matplotlib-%23ffffff.svg?style=for-the-badge&logo=Matplotlib&logoColor=black
https://img.shields.io/badge/Jupyter-%23FA0F00.svg?style=for-the-badge&logo=jupyter&logoColor=white
https://img.shields.io/badge/Hugging%20Face-FFD21E?style=for-the-badge&logo=huggingface&logoColor=black
https://img.shields.io/badge/Claude-D97757?style=for-the-badge&logo=claude&logoColor=white
https://img.shields.io/badge/OpenAI-%23412991.svg?style=for-the-badge&logo=openai&logoColor=white
```

## Frontend

```
https://img.shields.io/badge/react-%2320232a.svg?style=for-the-badge&logo=react&logoColor=%2361DAFB
https://img.shields.io/badge/Next.js-black?style=for-the-badge&logo=next.js&logoColor=white
https://img.shields.io/badge/tailwindcss-%2338B2AC.svg?style=for-the-badge&logo=tailwind-css&logoColor=white
https://img.shields.io/badge/vite-%23646CFF.svg?style=for-the-badge&logo=vite&logoColor=white
https://img.shields.io/badge/postcss-DD3A0A.svg?style=for-the-badge&logo=postcss&logoColor=white
https://img.shields.io/badge/svelte-%23f1413d.svg?style=for-the-badge&logo=svelte&logoColor=white
```

## Backend and infrastructure

```
https://img.shields.io/badge/node.js-6DA55F?style=for-the-badge&logo=node.js&logoColor=white
https://img.shields.io/badge/express.js-%23404d59.svg?style=for-the-badge&logo=express&logoColor=%2361DAFB
https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi&logoColor=white
https://img.shields.io/badge/flask-%23000.svg?style=for-the-badge&logo=flask&logoColor=white
https://img.shields.io/badge/vercel-%23000000.svg?style=for-the-badge&logo=vercel&logoColor=white
https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white
https://img.shields.io/badge/postgres-%23316192.svg?style=for-the-badge&logo=postgresql&logoColor=white
https://img.shields.io/badge/sqlite-%2307405e.svg?style=for-the-badge&logo=sqlite&logoColor=white
https://img.shields.io/badge/redis-%23DD0031.svg?style=for-the-badge&logo=redis&logoColor=white
```

## Tooling

```
https://img.shields.io/badge/git-%23F05033.svg?style=for-the-badge&logo=git&logoColor=white
https://img.shields.io/badge/GitHub%20Actions-%232671E5.svg?style=for-the-badge&logo=githubactions&logoColor=white
https://img.shields.io/badge/pytest-%230A9EDC.svg?style=for-the-badge&logo=pytest&logoColor=white
https://img.shields.io/badge/vitest-%236E9F18.svg?style=for-the-badge&logo=vitest&logoColor=white
https://img.shields.io/badge/pnpm-%23F69220.svg?style=for-the-badge&logo=pnpm&logoColor=white
```

## Status badges

These read live, so they belong in one row near the top, separate from the tech-stack rows.

```
[![CI](https://github.com/<owner>/<repo>/actions/workflows/ci.yml/badge.svg)](https://github.com/<owner>/<repo>/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-1a5fb4.svg)](LICENSE)
![Node](https://img.shields.io/badge/node-%E2%89%A5%2022.13-3c873a.svg)
![Python](https://img.shields.io/badge/python-%E2%89%A5%203.11-3670A0.svg)
```

`%E2%89%A5` is the encoded form of a "greater than or equal" sign, which is why those two look odd.

## Group template

```html
<!--- Category name --->
<p align="center"><sub><b>Category label:</b></sub></p>
<p align="center">
  <img src="URL_1">
  <img src="URL_2">
</p>
```

Three or four groups at most. Language and frameworks, infrastructure, tooling, then status.
