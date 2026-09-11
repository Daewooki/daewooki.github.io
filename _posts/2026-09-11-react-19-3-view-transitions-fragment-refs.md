---
title: "React 19.3: View Transitions·Fragment Refs 프로덕션 설계"
description: "라우팅·Suspense·상태 업데이트를 View Transitions로 엮을 때의 실패 케이스와 폴백, Fragment Refs 적용 경계를 정리합니다."
date: 2026-09-11 10:10:09 +0900
categories: ["News", "Frontend"]
tags: ["react", "view-transitions", "fragment-refs", "suspense", "routing", "trusted-types"]
render_with_liquid: false
---

## 2026-09-09에 바뀐 사실: 이제 실험이 아니라 계약이 됐다
React 팀은 2026-09-09에 React 19.3을 공개했고, 작년에 experimental로 소개했던 View Transitions와 Fragment Refs를 stable로 올렸습니다. React 19.3은 npm에서 바로 설치 가능한 정식 릴리스라는 선언까지 포함합니다. [React 19.3 발표문](https://react.dev/blog/2026/09/09/react-19-3)[^1]

여기서 중요한 포인트는 기능 목록이 아닙니다. stable로 승격되는 순간부터는 팀 단위로 “적용/미적용” 의사결정을 해야 하고, 적용한다면 실패 시나리오와 폴백을 제품 요구사항으로 끌어올려야 합니다. View Transitions는 UX 연출 도구로 보이지만, 실제로는 **라우팅과 상태 업데이트를 어떻게 분류하고 스케줄링할지**에 대한 설계 문제를 강제로 꺼내 놓습니다.[^1]

## View Transitions를 라우팅에 붙일 때 먼저 정해야 하는 것
React의 `<ViewTransition>`은 “업데이트가 Transition으로 마킹되었을 때”만 동작합니다. `startTransition` 내부의 state update, `<Suspense>` reveal, `useDeferredValue`로 촉발된 업데이트가 애니메이션 대상으로 간주됩니다. [React 19.3 발표문](https://react.dev/blog/2026/09/09/react-19-3)[^1]

이 말은 곧, 라우팅을 단순히 `setRoute(next)`로 처리하던 코드가 다음 중 하나를 선택해야 한다는 뜻입니다.

1) 라우팅은 “긴급하지 않다”로 분류하고 `startTransition`으로 감싼다.
2) 라우팅은 “긴급하다”로 분류하고 즉시 반영한다. 대신 라우팅에 딸린 일부 UI(예: 카드, 썸네일, 헤더)만 Transition 대상으로 만든다.

내 경험상 1)로 시작하면 초기 인상은 좋습니다. 페이지 이동이 부드러워지니까요. 하지만 서비스가 커질수록 2)로 수렴하는 경우가 많았습니다. 이유는 단순합니다. 라우팅은 UI 업데이트 중에서도 비즈니스 로직과 결합되는 지점이 많고, 여기서 한 번이라도 “사용자가 클릭했는데 화면이 안 바뀐 것처럼 느끼는” 순간이 나오면 View Transition의 이득을 한 번에 까먹습니다.

React 문서가 반복해서 암시하는 방향도 비슷합니다. 애니메이션은 urgent update를 방해하면 안 되고, Transition 업데이트는 batching/중단/재시작이 전제입니다. `startTransition`의 성격 자체가 “중요하지만 급하지 않은 업데이트”를 위한 API입니다. [startTransition](https://react.dev/reference/react/startTransition)[^2]

정리하면, 라우팅 전체를 Transition으로 둘지 여부는 UI 성향이 아니라 제품의 에러 허용도와 직결됩니다.

## `<ViewTransition>`이 브라우저 API를 어떻게 감추는지: startViewTransition을 직접 부르지 말아야 하는 이유
브라우저 View Transition API의 엔트리는 `document.startViewTransition()`입니다. 이것 자체는 same-document(SPA) 전환을 위한 API이고, `updateCallback`이 resolve된 다음 프레임에서 전환이 시작되는 구조입니다. [MDN: Document.startViewTransition](https://developer.mozilla.org/en-US/docs/Web/API/Document/startViewTransition)[^3]

React의 `<ViewTransition>`은 이 API를 개발자가 직접 호출하게 만들지 않습니다. 문서에 명시적으로 “React가 내부에서 startViewTransition을 호출하므로 직접 호출하지 말라”고 되어 있고, 페이지에서 다른 주체가 ViewTransition을 실행 중이면 React가 그것을 interrupt할 수도 있다고 적혀 있습니다. 또한 여러 React ViewTransition이 겹치면 순차 실행하며, 첫 전환 도중 여러 업데이트가 발생하면 다음 전환이 B->C가 아니라 B->D로 뭉쳐질 수 있습니다. [<ViewTransition> 동작 설명](https://react.dev/reference/react/ViewTransition)[^4]

라우팅 관점에서 이 동작은 실전에서 꽤 중요합니다.

- 사용자가 연타로 라우팅을 두 번 이상 바꾸면, 중간 상태로 한 번 들렀다가 다시 나오는 애니메이션이 아니라 “최종 목적지로 점프하는 애니메이션”이 될 수 있습니다.
- 이건 버그가 아니라 React가 스케줄링을 통제하면서 얻는 일관성(그리고 성능)입니다.
- 따라서 View Transition을 “상태 머신의 모든 intermediate state를 보여주는 연출”로 쓰면 어긋납니다.

이 성질을 받아들이면 설계가 달라집니다. 애니메이션을 디테일로 잡는 게 아니라, 전환이 스킵/합쳐졌을 때도 UX가 깨지지 않게 만드는 쪽으로 가야 합니다.

## 실패 케이스 1: enter/exit 애니메이션이 안 걸리는 구조
React 문서에 아주 노골적인 Pitfall이 하나 있습니다. enter/exit가 발동하려면 `<ViewTransition>`이 컴포넌트의 최상단(정확히는 다른 DOM node보다 앞)이어야 하고, 위에 `<div>` 같은 wrapper가 있으면 enter/exit가 아예 트리거되지 않습니다. [<ViewTransition> Pitfall: top-level 제약](https://react.dev/reference/react/ViewTransition)[^4]

이 제약은 프로덕션에서 흔히 밟습니다.

- 레이아웃 컴포넌트가 항상 `<div className="page">...</div>`로 감싸는 경우
- 접근성/테스트 편의상 data-attribute wrapper를 얹는 경우
- 디자인 시스템의 `Stack`, `Box` 같은 컴포넌트가 실제 DOM을 하나 생성하는 경우

해결책은 “wrapper를 없애라”가 아닙니다. 대부분의 팀에서 wrapper는 필수입니다. 대신, enter/exit 애니메이션은 페이지 전체에는 포기하고 update/share 중심으로 가져가거나, `<Activity>` 같은 다른 메커니즘으로 state를 보존하면서 가시성만 토글하는 구조로 바꿔야 합니다(React 문서도 `<Activity>`와의 조합을 별도로 언급합니다). [<ViewTransition>과 <Activity>](https://react.dev/reference/react/ViewTransition)[^4]

## 실패 케이스 2: 이름 충돌로 share 전환이 터진다
shared element 전환은 `<ViewTransition name="...">`가 “삭제되는 트리”와 “추가되는 트리”에 같은 name으로 존재할 때 share 애니메이션을 실행하는 방식입니다. 이 자체는 직관적이지만, name의 유일성이 앱 전역에서 보장돼야 한다는 제약이 따라옵니다. 문서에도 “같은 name이 동시에 두 개 mount되면 에러”라고 명시되어 있고, 리스트 렌더링에서 `name="item"` 같은 코드는 바로 폭발합니다. [<ViewTransition> 중복 name 에러](https://react.dev/reference/react/ViewTransition)[^4]

프로덕션에서 이걸 안전하게 만들려면 다음 원칙이 필요합니다.

- name은 `feature-namespace + stable-id`로 만든다. 예: `catalog-product-image-42`
- 전역에서 재사용하는 name은 상수 모듈로 분리해 import해서 쓴다(문서에서도 이 패턴을 권합니다). [<ViewTransition> name 네임스페이스 권고](https://react.dev/reference/react/ViewTransition)[^4]
- “동시에 화면에 존재할 수 있는 것”은 같은 name을 쓰지 않는다. 예: 리스트의 모든 카드 이미지에 동일 name을 주면 안 된다.

이건 코딩 컨벤션이 아니라 런타임 안정성 문제라서, lint rule을 붙이거나 wrapper 유틸로 강제하는 편이 낫습니다.

## 상태/라우팅/애니메이션을 엮는 방법: addTransitionType를 ‘원인’으로 써야 한다
같은 state 결과라도 원인에 따라 다른 애니메이션을 선택해야 하는 경우가 많습니다.

- 같은 `/product/42`로 가더라도
  - 리스트에서 카드 클릭으로 들어갈 때는 “드릴다운” 느낌
  - 뒤로 가기로 돌아올 때는 “리턴” 느낌

React 19.3은 이를 위해 `addTransitionType(type)`를 stable API로 제공합니다. `startTransition` 스코프 안에서 호출하면, 그 Transition에 원인(type)을 붙이고, React는 이것을 browser view transition types에도 반영할 수 있다고 설명합니다. [addTransitionType](https://react.dev/reference/react/addTransitionType)[^5]

또한 Transition Types는 commit마다 reset되며, `<Suspense>` fallback은 `startTransition` 이후 타입을 연관하지만 “fallback에서 실제 콘텐츠 reveal”에는 타입이 유지되지 않을 수 있다는 caveat도 있습니다. 이건 로딩/전환을 섬세하게 제어하려는 경우 함정이 됩니다. [addTransitionType caveats](https://react.dev/reference/react/addTransitionType)[^5]

실전에서는 타입을 다음처럼 정의하는 편이 안전했습니다.

- `navigation-forward`, `navigation-back` 같은 큰 분류만 먼저 도입
- 제품 요구사항이 생길 때만 세부 타입 추가(예: `modal-open`, `tab-switch`, `filter-apply`)

타입을 세분화하면 CSS/JS 애니메이션 분기가 기하급수로 늘어납니다. View Transition은 “설명 가능한 최소한의 연출”로 유지해야 유지보수가 됩니다.

## Suspense를 얹으면 성능이 좋아질 수도, 나빠질 수도 있다
React 19.3 발표문은 View Transitions와 Suspense 통합을 강하게 밀고 있고, fallback->콘텐츠 reveal을 update 애니메이션으로 만들 수 있다고 설명합니다. [React 19.3: Suspense와 View Transitions](https://react.dev/blog/2026/09/09/react-19-3)[^1]

하지만 같은 글에서 바로 “캐시된 UI(이미 로딩이 끝난 UI)를 자주 애니메이션하면 UX가 오히려 둔해질 수 있다”는 경고도 합니다. fallback은 즉시 보여야 하고, fallback->final은 애니메이션으로 연결하되, 즉시 나타날 수 있는 것까지 매번 fade하면 체감 성능이 내려간다는 요지입니다. 그리고 이를 위해 `default="none"`으로 enter/exit를 끄고 update만 남기는 패턴(`update="auto" default="none"`)을 예시로 제시합니다. [React 19.3: Suspense 애니메이션 원칙](https://react.dev/blog/2026/09/09/react-19-3)[^1]

여기서 실제 서비스에 적용할 때의 판단 기준은 다음입니다.

- 데이터 로딩이 “가끔 느리다”면: fallback->final을 부드럽게 연결하는 게 이득
- 대부분 즉시 로딩된다면: 애니메이션이 오히려 input latency처럼 느껴질 수 있음
- 로딩이 잦고 길다면: 애니메이션보다 skeleton/레이아웃 안정성(CLS)과 상호작용 제약이 더 중요

View Transitions는 perceived performance를 다루는 도구이지, 실제 네트워크 성능을 올려주지 않습니다. 로딩이 긴 상태에서 애니메이션을 진하게 넣으면 “화려한데 느린 앱”이 됩니다.

## 브라우저 지원과 폴백: ‘작동 안 해도 정상’이 기본값이어야 한다
View Transition API는 브라우저 기능이고, 지원 범위가 100%가 아닙니다. MDN은 `document.startViewTransition()`을 Baseline 2025로 표기하면서도 “구형 기기/브라우저에서는 동작하지 않을 수 있다”고 명시합니다. [MDN: Document.startViewTransition](https://developer.mozilla.org/en-US/docs/Web/API/Document/startViewTransition)[^3]

Can I use 데이터에서도 단일 문서 View Transitions는 지원/비지원이 섞여 있음을 보여줍니다. [Can I use: View Transitions API (single-document)](https://caniuse.com/view-transitions)[^6]

게다가 “지원한다/안 한다”와 별개로 runtime에서 transition이 스킵되는 케이스가 있습니다. MDN은 문서가 `hidden` 상태(백그라운드 탭 등)에서 `document.startViewTransition()`이 호출되면 transition이 스킵될 수 있다고 적습니다. [MDN: Using the View Transition API](https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API/Using)[^7]

따라서 폴백 설계는 이렇게 가는 게 맞습니다.

- View Transition은 장식이다. 없으면 그냥 즉시 전환한다.
- 상태/라우팅 로직은 View Transition 유무와 독립이어야 한다.
- QA는 “애니메이션이 항상 나온다”가 아니라 “안 나와도 기능이 정상”을 기준으로 해야 한다.

추가로, React 문서는 `prefers-reduced-motion`을 직접 확인해서 애니메이션을 꺼야 한다고 강하게 권합니다. React가 자동으로 꺼주지 않습니다. [<ViewTransition>: prefers-reduced-motion 권고](https://react.dev/reference/react/ViewTransition)[^4]

## 실전 코드: 라우팅/데이터/Suspense를 ViewTransition으로 안전하게 묶기
아래 예시는 React Router 같은 프레임워크 라우터 없이, 서비스에서 흔히 하는 “history 기반 라우팅”을 최소 구현한 데모입니다. 핵심은 라우팅을 `startTransition`으로 감싸고, `addTransitionType`로 forward/back을 구분하며, share 전환을 위해 `name`을 유일하게 부여하는 구조입니다.

구성은 카드 리스트(`/`)에서 상품 상세(`/product/:id`)로 들어가고, back/forward에도 애니메이션 방향이 바뀌는 시나리오입니다. 데이터 로딩은 `Suspense`로 처리하고, 첫 진입에서만 fallback->final update 애니메이션이 나오도록 설계합니다.

### 설치 (Vite + React 19.3)
```bash
npm create vite@latest react19-vt-demo -- --template react-ts
cd react19-vt-demo

# React 19.3으로 맞춥니다.
npm i react@19.3.0 react-dom@19.3.0

npm run dev
```

개발 서버가 뜨면 `/`에서 카드를 클릭해 `/product/1`로 이동하고, 브라우저 back/forward도 같이 눌러봅니다.

예상 출력(터미널):
```text
  VITE vX.Y.Z  ready in XXX ms
  ➜  Local:   http://localhost:5173/
```

### 1) history 기반 라우터: forward/back 판별과 Transition Types
`src/router.ts`
```ts
import { startTransition, addTransitionType } from 'react';

export type Route =
  | { kind: 'list' }
  | { kind: 'product'; id: number };

function parseRoute(pathname: string): Route {
  if (pathname.startsWith('/product/')) {
    const id = Number(pathname.split('/product/')[1]);
    return { kind: 'product', id: Number.isFinite(id) ? id : 1 };
  }
  return { kind: 'list' };
}

function getNavIndexFromHistoryState(): number {
  const st = history.state as any;
  return typeof st?.__navIndex === 'number' ? st.__navIndex : 0;
}

export function initHistoryStateIfNeeded() {
  // 첫 로드에서 index가 없으면 0으로 심습니다.
  const current = getNavIndexFromHistoryState();
  if (history.state?.__navIndex === undefined) {
    history.replaceState({ ...(history.state ?? {}), __navIndex: current }, '', location.pathname);
  }
}

export function readRoute(): { route: Route; navIndex: number } {
  return { route: parseRoute(location.pathname), navIndex: getNavIndexFromHistoryState() };
}

export function navigateTo(pathname: string, nextNavIndex: number) {
  startTransition(() => {
    addTransitionType('navigation-forward');
    history.pushState({ __navIndex: nextNavIndex }, '', pathname);
    // popstate는 pushState에서는 발생하지 않으므로, 앱 쪽에서 직접 state를 갱신해야 합니다.
  });
}

export function installPopstateListener(
  onChange: (next: { route: Route; navIndex: number; direction: 'back' | 'forward' | 'unknown' }) => void
) {
  window.addEventListener('popstate', () => {
    const next = readRoute();
    // direction은 앱이 마지막으로 알고 있던 index와 비교해서 추론합니다.
    onChange({ ...next, direction: 'unknown' });
  });
}

export function markPopDirection(prevIndex: number, nextIndex: number) {
  if (nextIndex < prevIndex) return 'back' as const;
  if (nextIndex > prevIndex) return 'forward' as const;
  return 'unknown' as const;
}
```

여기서 중요한 점은 2가지입니다.

- `addTransitionType('navigation-forward')`는 “원인”을 붙입니다. 애니메이션 디테일은 CSS/이벤트에서 결정합니다. [addTransitionType](https://react.dev/reference/react/addTransitionType)[^5]
- `pushState`는 `popstate`를 발생시키지 않으므로, 라우팅 state는 앱이 직접 업데이트해야 합니다. 이건 프레임워크 라우터가 내부에서 해주던 일입니다.

### 2) 데이터 로딩: Suspense fallback을 ‘즉시’, reveal을 ‘update 애니메이션’으로
`src/data.ts`
```ts
export type Product = {
  id: number;
  name: string;
  price: number;
  imageUrl: string;
};

const PRODUCTS: Product[] = [
  { id: 1, name: 'Desk Lamp', price: 39, imageUrl: 'https://picsum.photos/id/1060/320/240' },
  { id: 2, name: 'Mug', price: 12, imageUrl: 'https://picsum.photos/id/30/320/240' },
  { id: 3, name: 'Headphones', price: 129, imageUrl: 'https://picsum.photos/id/180/320/240' },
];

const cache = new Map<string, Promise<any>>();

function sleep(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

export function listProducts(): Product[] {
  return PRODUCTS;
}

export function fetchProduct(id: number): Promise<Product> {
  const key = `product:${id}`;
  if (!cache.has(key)) {
    cache.set(
      key,
      (async () => {
        // 첫 진입에서만 suspense가 생기도록 지연을 넣습니다.
        await sleep(500);
        const p = PRODUCTS.find((x) => x.id === id);
        if (!p) throw new Error('Not found');
        return p;
      })()
    );
  }
  return cache.get(key)!;
}
```

이 예시는 “로딩이 처음만 느리고, 그 다음부터는 캐시로 즉시”라는 전형적인 패턴을 흉내냅니다. React 19.3 발표문이 말한 것처럼, 캐시된 UI까지 매번 애니메이션하면 둔해질 수 있으므로 enter/exit를 끄고 update에만 기대는 구성이 맞습니다. [React 19.3: Suspense 애니메이션 원칙](https://react.dev/blog/2026/09/09/react-19-3)[^1]

### 3) 페이지 구성: ViewTransition을 라우팅 셸에 두고, share는 이미지에만 둔다
`src/pages/ProductList.tsx`
```tsx
import { ViewTransition, startTransition } from 'react';
import { listProducts } from '../data';

export function ProductList(props: { onOpen: (id: number) => void }) {
  const products = listProducts();

  return (
    <div className="page">
      <h1>Catalog</h1>
      <div className="grid">
        {products.map((p) => (
          <button
            key={p.id}
            className="card"
            onClick={() => {
              // 클릭은 urgent로 처리하고 싶을 때도 있지만,
              // 여기서는 라우팅을 transition으로 설계한 데모라 startTransition으로 감쌉니다.
              startTransition(() => props.onOpen(p.id));
            }}
          >
            <ViewTransition name={`catalog-product-image-${p.id}`}>
              <img className="thumb" src={p.imageUrl} alt={p.name} />
            </ViewTransition>
            <div className="meta">
              <div className="name">{p.name}</div>
              <div className="price">${p.price}</div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
```

`src/pages/ProductDetail.tsx`
```tsx
import { Suspense, use, ViewTransition, startTransition } from 'react';
import { fetchProduct } from '../data';

function ProductDetailBody(props: { id: number; onBack: () => void }) {
  const product = use(fetchProduct(props.id));

  return (
    <div className="page">
      <div className="toolbar">
        <button
          onClick={() => {
            startTransition(() => props.onBack());
          }}
        >
          Back
        </button>
      </div>

      <div className="detail">
        <ViewTransition name={`catalog-product-image-${product.id}`}>
          <img className="hero" src={product.imageUrl} alt={product.name} />
        </ViewTransition>
        <div>
          <h1>{product.name}</h1>
          <p className="price">${product.price}</p>
          <p className="desc">
            This is a placeholder description. The important part is that the image shares the same
            ViewTransition name across list and detail.
          </p>
        </div>
      </div>
    </div>
  );
}

export function ProductDetail(props: { id: number; onBack: () => void }) {
  return (
    <Suspense fallback={<div className="page"><p className="loading">Loading…</p></div>}>
      <ProductDetailBody id={props.id} onBack={props.onBack} />
    </Suspense>
  );
}
```

여기서 share 전환은 이미지에만 걸었습니다. 페이지 전체를 share로 만들면 “너무 많은 게 움직이는” 문제가 생깁니다. React 문서도 share는 트리 깊은 곳에서도 발동할 수 있다고 설명하지만, 그만큼 의도치 않은 공유가 발생하기 쉽습니다. [<ViewTransition> share 개념](https://react.dev/reference/react/ViewTransition)[^4]

그리고 name은 반드시 `id`를 포함해 유일하게 만들었습니다. 리스트의 모든 카드에 `name="item"`처럼 주면, 동시에 여러 개가 mount되어 바로 에러가 납니다. [<ViewTransition> 중복 name 에러](https://react.dev/reference/react/ViewTransition)[^4]

### 4) App 셸: 라우트 전환 자체는 update 애니메이션 중심으로
`src/App.tsx`
```tsx
import { useEffect, useMemo, useState, ViewTransition, startTransition, addTransitionType } from 'react';
import { ProductList } from './pages/ProductList';
import { ProductDetail } from './pages/ProductDetail';
import {
  initHistoryStateIfNeeded,
  installPopstateListener,
  markPopDirection,
  navigateTo,
  readRoute,
  type Route,
} from './router';
import './view-transitions.css';
import './ui.css';

type NavState = { route: Route; navIndex: number };

export default function App() {
  const [nav, setNav] = useState<NavState>(() => {
    initHistoryStateIfNeeded();
    return readRoute();
  });

  useEffect(() => {
    installPopstateListener((next) => {
      const dir = markPopDirection(nav.navIndex, next.navIndex);

      startTransition(() => {
        addTransitionType(dir === 'back' ? 'navigation-back' : 'navigation-forward');
        setNav({ route: next.route, navIndex: next.navIndex });
      });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nav.navIndex]);

  const content = useMemo(() => {
    if (nav.route.kind === 'product') {
      return (
        <ProductDetail
          id={nav.route.id}
          onBack={() => {
            history.back();
          }}
        />
      );
    }
    return (
      <ProductList
        onOpen={(id) => {
          const nextIndex = nav.navIndex + 1;
          navigateTo(`/product/${id}`, nextIndex);
          // pushState 이후 App이 직접 nav state를 갱신합니다.
          startTransition(() => {
            addTransitionType('navigation-forward');
            setNav({ route: { kind: 'product', id }, navIndex: nextIndex });
          });
        }}
      />
    );
  }, [nav.navIndex, nav.route]);

  // 라우트 셸 자체는 update 애니메이션만 쓰는 편이 안전합니다.
  // enter/exit는 top-level 제약 때문에 레이아웃 구조와 충돌하기 쉽습니다.
  return (
    <ViewTransition update="auto" default="none"
      update={{
        'navigation-forward': 'page-forward',
        'navigation-back': 'page-back',
        default: 'page-default',
      }}
    >
      {content}
    </ViewTransition>
  );
}
```

포인트를 정리하면 이렇습니다.

- 루트 `<ViewTransition>`은 `default="none"`으로 enter/exit를 끄고 update에만 기대는 설계입니다. 캐시된 화면이 즉시 나타날 때는 애니메이션이 최소화됩니다(React 발표문이 권한 원칙에 가깝습니다). [React 19.3: Suspense 애니메이션 원칙](https://react.dev/blog/2026/09/09/react-19-3)[^1]
- forward/back은 `addTransitionType`로만 구분합니다. 타입은 CSS 클래스 선택으로 내려갑니다. [addTransitionType: View Transition Class 매핑](https://react.dev/reference/react/addTransitionType)[^5]
- share는 이미지처럼 “사용자가 동일 개체라고 인식하는 요소”에만 둡니다.

### 5) CSS: prefers-reduced-motion과 타입별 방향만 최소 구현
`src/view-transitions.css`
```css
@media (prefers-reduced-motion: reduce) {
  ::view-transition-group(.page-forward),
  ::view-transition-group(.page-back),
  ::view-transition-group(.page-default) {
    animation-duration: 1ms !important;
  }
}

/* 기본: cross-fade를 조금 더 짧게 */
::view-transition-old(.page-default),
::view-transition-new(.page-default) {
  animation-duration: 180ms;
}

/* forward/back: 살짝 밀어주는 정도만 */
::view-transition-old(.page-forward) {
  animation: vt-slide-out-left 220ms ease both;
}
::view-transition-new(.page-forward) {
  animation: vt-slide-in-right 220ms ease both;
}

::view-transition-old(.page-back) {
  animation: vt-slide-out-right 220ms ease both;
}
::view-transition-new(.page-back) {
  animation: vt-slide-in-left 220ms ease both;
}

@keyframes vt-slide-in-right {
  from { transform: translateX(10px); opacity: 0.9; }
  to { transform: translateX(0); opacity: 1; }
}
@keyframes vt-slide-out-left {
  from { transform: translateX(0); opacity: 1; }
  to { transform: translateX(-10px); opacity: 0.9; }
}
@keyframes vt-slide-in-left {
  from { transform: translateX(-10px); opacity: 0.9; }
  to { transform: translateX(0); opacity: 1; }
}
@keyframes vt-slide-out-right {
  from { transform: translateX(0); opacity: 1; }
  to { transform: translateX(10px); opacity: 0.9; }
}
```

React 문서가 강조하듯 `prefers-reduced-motion`은 자동 처리가 아니고, 개발자가 책임져야 합니다. [<ViewTransition>: prefers-reduced-motion 권고](https://react.dev/reference/react/ViewTransition)[^4]

또한 이 CSS는 “작동하면 좋고, 안 되면 아무 일도 안 일어나는” 형태입니다. `::view-transition-*` 셀렉터는 View Transition이 활성화되지 않으면 매칭이 되지 않으니, 비지원 브라우저에서도 기능적으로는 그대로 굴러갑니다.

### 6) UI CSS (데모용)
`src/ui.css`
```css
body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; }
.page { padding: 16px; max-width: 920px; margin: 0 auto; }
.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.card { text-align: left; border: 1px solid #ddd; background: white; border-radius: 10px; padding: 10px; cursor: pointer; }
.thumb { width: 100%; height: 140px; object-fit: cover; border-radius: 8px; display: block; }
.hero { width: 420px; height: 320px; object-fit: cover; border-radius: 12px; display: block; }
.detail { display: grid; grid-template-columns: 440px 1fr; gap: 16px; align-items: start; }
.toolbar { margin-bottom: 12px; }
.loading { opacity: 0.7; }
.price { font-weight: 600; }
```

이 데모가 보여주는 건 “애니메이션을 예쁘게”가 아니라, 라우팅/로딩/방향성까지 포함해서 기능이 깨지지 않는 최소 단위의 결합 방식입니다.

## ViewTransition 이벤트를 써야 하는 경우: 외부 애니메이션 엔진/취소가 필요할 때
React `<ViewTransition>`은 `onEnter`, `onExit`, `onShare`, `onUpdate` 이벤트 props를 제공하고, 각 이벤트는 cleanup 함수를 반환해야 합니다. 이 cleanup은 transition 종료 시점에 호출되어 애니메이션 취소/정리가 가능하다고 문서에 명시되어 있습니다. [<ViewTransition> 이벤트/cleanup 규칙](https://react.dev/reference/react/ViewTransition)[^4]

이 패턴이 필요한 경우는 대략 두 가지였습니다.

1) Web Animations API로 pseudo-element에 직접 animate를 걸고 싶을 때
2) 라우팅이 스킵/합쳐질 때 진행 중인 애니메이션을 강제로 취소해야 할 때

특히 React는 “다른 주체가 시작한 ViewTransition을 interrupt할 수 있다”고 했기 때문에, 앱이 외부에서 `document.startViewTransition()`을 쓰거나, 여러 마이크로프론트엔드가 공존하는 경우에는 충돌이 날 수 있습니다. React가 통제하는 경계 안으로 몰아넣는 편이 낫습니다. [<ViewTransition> 내부 동작과 interrupt](https://react.dev/reference/react/ViewTransition)[^4]

## Fragment Refs: wrapper 제거가 아니라 ‘컴포저블한 DOM 조작’으로 쓰는 기능
Fragment Refs는 `<Fragment ref={...}>`로 `FragmentInstance`를 얻고, 그 인스턴스를 통해 “Fragment의 DOM children을 그룹으로” 다루게 해줍니다. React 19.3에서 stable입니다. [React 19.3: Fragment Refs](https://react.dev/blog/2026/09/09/react-19-3)[^1]

여기서 기대치 조절이 필요합니다. 이건 “모든 DOM을 마음대로 조작할 수 있는 escape hatch”가 아닙니다. 문서에 적힌 기능들은 상당히 제한적이고, 오히려 그 제한 덕분에 컴포넌트 경계를 덜 깨면서 플랫폼 기능을 조합할 수 있습니다.

대표적으로 다음이 가능합니다.

- wrapper 없이 여러 sibling에 click listener를 붙이기(`addEventListener`/`removeEventListener`)
- 여러 필드로 구성된 폼에서 focus 이동을 그룹 단위로 처리(`focus`, `focusLast`, `blur`)
- IntersectionObserver/ResizeObserver를 child들에 한 번에 붙이기(`observeUsing`/`unobserveUsing`)
- 여러 child의 bounding rect를 한 번에 계산(`getClientRects`)

이 중 실전 가치가 큰 건 `observeUsing`입니다. 카드 컴포넌트가 라이브러리에서 왔고 ref forwarding이 없어서 노출 추적이 곤란한 경우가 흔한데, Fragment Ref는 이를 “컴포넌트를 수정하지 않고” 해결할 수 있습니다. [Fragment observeUsing](https://react.dev/reference/react/Fragment)[^8]

## Fragment Refs의 실패 케이스: 첫 번째 레벨만 잡는다
Fragment Refs는 만능이 아니고, 어디까지 target으로 잡는지 규칙이 명확합니다.

- `addEventListener`, `observeUsing`, `getClientRects` 같은 “children 타겟” 메서드는 Fragment의 first-level host(DOM) children만 대상으로 합니다.
- 반면 `focus`/`focusLast`는 depth-first로 nested child까지 찾아갑니다.
- `observeUsing`은 text node에는 동작하지 않고, Fragment에 text만 있으면 dev에서 warning이 납니다.

이 caveat는 문서에 그대로 적혀 있습니다. [FragmentInstance caveats](https://react.dev/reference/react/Fragment)[^8]

이 제약은 실무에서 오히려 안전장치로 작동하는 면이 있습니다.

- 이벤트 리스너를 “모든 하위 DOM”에 무차별로 걸지 않습니다.
- 관찰 대상이 wrapper 내부로 깊게 들어가면, 컴포넌트 구성 변경에 따라 의미가 깨질 수 있는데, Fragment Ref는 그걸 막습니다.

반대로 말하면, 디자인 시스템이 내부적으로 `<div>`를 하나 더 만든다거나, 카드가 내부에 또 wrapper를 만들면 관찰 대상이 바뀔 수 있습니다. Fragment Refs를 도입하면 “DOM 구조 변경이 행동 의미를 바꾼다”는 사실이 더 선명해집니다.

## React 19.3의 Trusted Types 지원: 성능보다 ‘보안 계약’이 바뀐다
React 19.3에는 View Transitions/Fragment Refs 외에도 React DOM 쪽 변경이 있습니다. 그중 프론트 팀에 직접 영향을 주는 게 Trusted Types 지원입니다.

React 19.3은 Trusted Types API와 통합되며, CSP에서 `require-trusted-types-for 'script'`를 강제하는 사이트에서 React가 Trusted Types 객체(`TrustedHTML`, `TrustedScript`, `TrustedScriptURL`)를 문자열로 강제 변환하지 않고 그대로 DOM sink로 전달하도록 바뀌었습니다. 과거에는 React가 `'' + value`로 문자열 coercion을 해버려서 Trusted Types 객체가 plain string이 되어 브라우저에 의해 reject될 수 있었다고 설명합니다. [React 19.3: Trusted Types support](https://react.dev/blog/2026/09/09/react-19-3)[^1]

Trusted Types 자체는 DOM-based XSS를 줄이기 위한 브라우저 보안 메커니즘입니다. [MDN: Trusted Types API](https://developer.mozilla.org/en-US/docs/Web/API/Trusted_Types_API)[^9]  
표준 문서도 별도로 존재합니다. [W3C: Trusted Types](https://www.w3.org/TR/trusted-types/)[^10]

이 변화는 UX/성능과 직접 연결되진 않지만, “보안 정책을 켠 대규모 서비스”에서는 릴리스 마이그레이션의 비용을 바꿉니다.

- 기존: Trusted Types 강제 + React 렌더링이 충돌할 수 있어 적용 범위가 제한됨
- 19.3 이후: 최소한 “React가 억지로 string으로 만들어 깨뜨리는 문제”는 줄어듦

다만 이것은 자동으로 안전해지는 게 아닙니다. Trusted Types는 정책을 설계하고 sanitization pipeline을 운영할 때 의미가 있습니다.

## 지금 시점(2026-09-11 KST)에 프로덕션 적용을 판단하는 체크리스트
### 1) 라우팅을 Transition으로 묶을지부터 결정
- “항상 부드럽게”가 목표면: 라우팅 state update를 `startTransition`으로 감싸되, 연타/중복 네비게이션에서 업데이트가 합쳐지는 동작을 UX로 수용해야 합니다. [<ViewTransition> batching 동작](https://react.dev/reference/react/ViewTransition)[^4]
- “클릭 즉시 반응”이 목표면: 라우팅은 urgent로 두고, share 대상(썸네일/헤더)만 `<ViewTransition>`로 좁히는 쪽이 안전합니다.

### 2) enter/exit보다 update/share를 우선
enter/exit는 top-level 제약 때문에 컴포넌트 구조와 충돌이 잦습니다. update/share는 상대적으로 구조 제약이 약하고, 공유 요소만 움직이게 하면 연출이 과해지지 않습니다. [<ViewTransition> Pitfall: top-level 제약](https://react.dev/reference/react/ViewTransition)[^4]

### 3) name은 네임스페이스+id로 강제
중복 name은 개발 환경에서 즉시 에러를 띄웁니다. 리스트/그리드/가상 스크롤에서는 더 쉽게 밟습니다. [<ViewTransition> 중복 name 에러](https://react.dev/reference/react/ViewTransition)[^4]

### 4) Suspense 애니메이션은 ‘fallback 즉시, reveal만’ 원칙
React 발표문이 제시한 원칙 그대로 가져가야 합니다. 캐시된 UI에까지 fade를 걸면 사용자가 입력 지연으로 느낍니다. [React 19.3: Suspense 애니메이션 원칙](https://react.dev/blog/2026/09/09/react-19-3)[^1]

### 5) 브라우저 지원/스킵을 전제로 QA 시나리오를 짠다
- 비지원 브라우저: 애니메이션 없이 기능이 정상
- 지원 브라우저라도 runtime에서 스킵 가능(백그라운드 탭 등) [MDN: Using the View Transition API](https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API/Using)[^7]
- 지원 범위는 Can I use로 팀 내부 기준선을 만든다 [Can I use: View Transitions API (single-document)](https://caniuse.com/view-transitions)[^6]

### 6) prefers-reduced-motion은 필수
React가 자동으로 처리해주지 않습니다. CSS 레벨에서라도 최소한 duration을 1ms로 줄이는 식으로 대응해야 합니다. [<ViewTransition>: prefers-reduced-motion 권고](https://react.dev/reference/react/ViewTransition)[^4]

## 결론: View Transitions는 애니메이션 API가 아니라 라우팅/로딩 설계 도구다
React 19.3에서 View Transitions와 Fragment Refs가 stable이 되면서, 프론트엔드의 기본기가 한 단계 바뀐 느낌이 있습니다. View Transitions는 “멋있는 효과”가 아니라 라우팅과 로딩을 Transition으로 분류하고, 그 결과를 브라우저 레벨 애니메이션으로 일관되게 표현하는 메커니즘입니다. [React 19.3 발표문](https://react.dev/blog/2026/09/09/react-19-3)[^1]

Fragment Refs는 wrapper를 없애는 편의 기능으로 보면 반만 봅니다. 실제 가치는 라이브러리 컴포넌트를 뜯지 않고도 event/observer/focus 같은 플랫폼 동작을 컴포저블하게 얹을 수 있다는 점이고, 동시에 first-level DOM child로 제한된 규칙 덕분에 무분별한 DOM 조작을 막아줍니다. [FragmentInstance caveats](https://react.dev/reference/react/Fragment)[^8]

프로덕션에서는 “전환이 항상 된다”를 전제로 하지 않고, “전환이 없어도 제품이 완전하다”를 전제로 설계하는 순간부터 적용 가치가 생깁니다.

## 참고 자료
- [React 19.3 발표문](https://react.dev/blog/2026/09/09/react-19-3)
- [React GitHub Releases: 19.3.0](https://github.com/react/react/releases)
- [<ViewTransition>](https://react.dev/reference/react/ViewTransition)
- [addTransitionType](https://react.dev/reference/react/addTransitionType)
- [<Fragment> (Fragment Refs 포함)](https://react.dev/reference/react/Fragment)
- [startTransition](https://react.dev/reference/react/startTransition)
- [MDN: View Transition API](https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API)
- [MDN: Document.startViewTransition](https://developer.mozilla.org/en-US/docs/Web/API/Document/startViewTransition)
- [MDN: Using the View Transition API](https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API/Using)
- [Can I use: View Transitions API (single-document)](https://caniuse.com/view-transitions)
- [WICG: view-transitions](https://github.com/WICG/view-transitions)
- [React 19.3: Trusted Types support](https://react.dev/blog/2026/09/09/react-19-3)
- [MDN: Trusted Types API](https://developer.mozilla.org/en-US/docs/Web/API/Trusted_Types_API)
- [W3C: Trusted Types](https://www.w3.org/TR/trusted-types/)

[^1]: <https://react.dev/blog/2026/09/09/react-19-3>
[^2]: <https://react.dev/reference/react/startTransition>
[^3]: <https://developer.mozilla.org/en-US/docs/Web/API/Document/startViewTransition>
[^4]: <https://react.dev/reference/react/ViewTransition>
[^5]: <https://react.dev/reference/react/addTransitionType>
[^6]: <https://caniuse.com/view-transitions>
[^7]: <https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API/Using>
[^8]: <https://react.dev/reference/react/Fragment>
[^9]: <https://developer.mozilla.org/en-US/docs/Web/API/Trusted_Types_API>
[^10]: <https://www.w3.org/TR/trusted-types/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
