---
title: "Android Security Bulletin 패치 레벨을 플릿 운영 계약으로 굳히는 법"
description: "ASB의 2026-11-01/2026-11-05 이중 패치 레벨을 정책·롤아웃·앱/백엔드 최소 보안 버전으로 연결해 플릿 운영 계약으로 고정합니다."
date: 2026-11-13 12:10:31 +0900
categories: ["Mobile", "Android Security Bulletin"]
tags: ["android", "security-patch-level", "fleet-ops", "android-enterprise", "play-integrity", "risk-based-rollout"]
render_with_liquid: false
---

## 2026-11 ASB를 운영 계약 단위로 봐야 하는 이유

AOSP의 [Android Security Bulletin—November 2026](https://source.android.com/docs/security/bulletin/2026/2026-11-01)는 **2026년 11월 2일** 게시되었고, **2026년 11월 6일**에 업데이트되었습니다. 게시물 상단에 Published/Updated가 명시돼 있고, 하단의 Versions 표에 1.0(게시)과 1.1(Add AOSP links)가 기록돼 있습니다. 즉, 이달 공지는 단순히 CVE 목록이 아니라 “패치가 AOSP에 올라왔고 링크가 붙었다”까지 포함해 운영 타이밍을 확정할 수 있는 상태로 바뀐 것입니다. [Android Security Bulletin—November 2026](https://source.android.com/docs/security/bulletin/2026/2026-11-01)

그리고 이 공지는 보안 패치 레벨이 둘입니다. [Android Security Bulletins](https://source.android.com/docs/security/bulletin/asb-overview)에도 2026년 11월 항목이 2026-11-01 / 2026-11-05로 표시됩니다. 이 구조는 이미 익숙하지만, 플릿 운영 관점에서는 의미가 더 무겁습니다.

- 운영팀이 합의해야 하는 것은 CVE가 아니라 “우리 조직은 2026-11-01을 언제까지, 2026-11-05를 언제까지 요구하는가”입니다.
- 보안팀이 합의해야 하는 것은 심각도 라벨이 아니라 “업무 영향(업데이트 실패/재부팅 필요/업무 중단)을 감수하고도 11-01을 즉시 강제할 정도인가, 아니면 11-05까지 기다려도 되는가”입니다.
- 앱/백엔드가 합의해야 하는 것은 “OS version 최소치”보다 더 현실적인 “보안 상태 최소치”입니다.

나는 예전에 패치 레벨을 기준으로 플릿을 굴리는 방식 자체는 정리해 둔 적이 있습니다.
- [Android Security Bulletin 패치 레벨로 플릿 업데이트 운영하기](https://daewooki.github.io/posts/android-spl-fleet-operations/)
- [Android Security Bulletin 2026-09로 다시 짜는 모바일 보안 업데이트 운영](https://daewooki.github.io/posts/android-security-bulletin-patch-level-ops/)

이번 글에서는 같은 얘기를 반복하지 않고, **2026-11 공지의 11-01/11-05 분리를 전제로** 이를 플릿 운영 계약(정책 문장 + 예외 조항 + 롤아웃 규칙 + 집행 포인트)으로 굳히는 방법만 파고듭니다.

## 2026-11-01과 2026-11-05: 무엇이 달라지고 무엇이 같나

이번 공지는 “패치 레벨 2026-11-05 또는 그 이후가 모든 이슈를 해결한다”고 못 박습니다. 공지 본문 첫 부분에 “Security patch levels of 2026-11-05 or later address all of these issues.”가 직접 적혀 있습니다. [Android Security Bulletin—November 2026](https://source.android.com/docs/security/bulletin/2026/2026-11-01)

또한 공지의 Common questions and answers에 다음 규칙을 명시합니다.

- 2026-11-01 이상은 2026-11-01 묶음에 해당하는 이슈를 해결합니다.
- 2026-11-05 이상은 2026-11-05 묶음 + 이전 패치 레벨을 모두 포함합니다.
- 제조사는 시스템 프로퍼티 `ro.build.version.security_patch`를 `2026-11-01` 또는 `2026-11-05`로 설정해야 한다고 적혀 있습니다. [Android Security Bulletin—November 2026](https://source.android.com/docs/security/bulletin/2026/2026-11-01)

이 구조가 플릿 운영 계약의 핵심이 되는 이유는 간단합니다.

- 11-01은 Android runtime / Framework / System처럼 AOSP 공통층이 중심입니다.
- 11-05는 kernel + SoC/vendor 컴포넌트가 중심입니다.

이 구분 자체는 연구/분석 문서에서도 partial SPL(01)과 complete SPL(05)로 설명됩니다. FTC 쪽 공개 보고서에서도 “partial SPL은 YYYY-MM-01, complete SPL은 YYYY-MM-05”이며 complete가 closed-source 컴포넌트(예: Qualcomm)까지 포함한다고 적습니다. (현장에서 체감하는 OEM 지연이 왜 05에서 더 심해지는지 설명이 깔끔해집니다.) [50 Shades of Support: A Device-Centric Analysis of Android Security Updates](https://www.ftc.gov/system/files/ftc_gov/pdf/16-Acar-A-Device-Centric-Analysis-of-Android-Security-Updates.pdf)

그리고 이번 달의 가장 심각한 이슈로 공지 본문은 Framework의 Critical RCE를 지목합니다. “추가 권한 불필요, 사용자 상호작용 불필요”라고 서술되어 있고, Framework 테이블의 첫 줄이 CVE-2026-58868(Critical, RCE)로 박혀 있습니다. [Android Security Bulletin—November 2026](https://source.android.com/docs/security/bulletin/2026/2026-11-01)

여기서 운영적으로 중요한 결론은 하나입니다.

- 11-01은 즉시성(Framework/System 계열) 대응의 하한선이 됩니다.
- 11-05는 플릿 전체를 “완료 상태”로 분류하기 위한 상한선(정상화 기준)이 됩니다.

따라서 조직 정책을 만들 때 “이번 달은 11월 패치 하세요” 같은 문장은 아무 쓸모가 없습니다. 계약 문장은 반드시 11-01과 11-05를 분리해서 써야 합니다.

## 패치 레벨 매트릭스: SPL 하나로는 부족해진 이유

SPL을 `YYYY-MM-DD`라는 문자열 하나로 다루면, 관리가 쉬운 대신 오판이 생깁니다. Android가 점점 모듈화되면서 업데이트 채널이 나뉘었기 때문입니다.

Android는 이 문제를 정면으로 다루기 시작했고, AndroidX 쪽에 Security State 라이브러리를 내면서 SPL을 여러 축으로 보라고 가이드합니다. Android Developers 문서에는 DSPL(Device SPL), ASPL(Available SPL), PSPL(Published SPL)을 조합해서 “민감 기능 게이팅”을 하라고 적혀 있습니다. [Understand device security state](https://developer.android.com/privacy-and-security/understand-device-security-state)

또 Android Developers Blog는 단일 SPL이 coarse하다고 지적하면서, system / system modules(Project Mainline) / kernel을 나눠서 보라고 말합니다. [Introducing the AndroidX Security State Libraries](https://developer.android.com/blog/posts/introducing-the-android-x-security-state-libraries-a-unified-view-of-device-security)

Google Security Blog 글도 같은 결론을 강조합니다. 설치된 것(installed), 공지된 것(published), 설치 대기(pending)까지 합쳐서 Effective Security State를 만들자는 방향입니다. [Android Security State Libraries](https://blog.google/security/android-security-state-libraries/)

다만, 플릿 운영 계약을 만드는 관점에서는 너무 복잡해지면 실패합니다. 그래서 나는 매트릭스를 2층으로 나눕니다.

1) 계약(Policy) 레벨: ASB의 01/05를 “월간 릴리스 단위”로 고정한다.
2) 집행(Enforcement) 레벨: 단말/MDM/앱이 확보 가능한 신호 범위에서 system/modules/kernel을 추가로 본다.

여기서 매트릭스의 목적은 하나입니다.

- 같은 2026-11-01이라도, 어떤 기기는 사실상 mainline은 최신인데 system OTA만 밀렸을 수 있습니다.
- 반대로 2026-11-05라고 찍혀 있어도, vendor partition의 patch 정보가 허술하게 운영되는 OEM이 섞이면 신뢰도가 흔들릴 수 있습니다.

AVB(Verified Boot) 관점에서도 partition마다 security patch level을 다룬다는 문서가 있습니다. 빌드 시스템이 `com.android.build.${partition}.security_patch`를 `YYYY-MM-DD` 포맷으로 쓰고, 제조사가 `VENDOR_SECURITY_PATCH` 같은 값을 세팅해야 한다고 설명합니다. 즉, 운영적으로는 “SPL 11-05 하나”로 퉁치는 순간 partition 간 비대칭이 숨어버립니다. [Version information in AVB properties](https://source.android.com/docs/core/architecture/bootloader/version-info-avb)

### 내가 쓰는 최소 매트릭스(정책 문서에 그대로 넣는 형태)

정책 문서에는 보통 다음 4칸이면 충분합니다.

| 구분 | 신호 소스 | 최소 요구(하한) | 정상화(상한) |
|---|---|---:|---:|
| 회사 소유(fully managed/COPE) | MDM compliance / Android Management API | 2026-11-01 | 2026-11-05 |
| BYOD(work profile) | MDM(가능하면) + 앱 신호 | 2026-11-01 | 2026-11-05(유예) |
| 비관리(unmanaged) | Play Integrity + 앱 신호 | 강제는 신중(기능 제한 위주) | Strong Integrity 기반 |
| 예외(레거시/업무필수) | 승인 + 네트워크 격리 | 2026-11-01 도달이 목표 | 2026-11-05는 케이스 바이 케이스 |

여기서 “신호 소스”가 실제 집행 가능성을 결정합니다.

- Android 앱 내부에서는 `Build.VERSION.SECURITY_PATCH`로 user-visible SPL을 읽을 수 있습니다. [Build.VERSION API reference](https://developer.android.com/reference/android/os/Build.VERSION.html)
- Android Enterprise/MDM 쪽에서는 최소 SPL을 compliance rule로 걸 수 있습니다(예: Intune에서 Minimum security patch level). [Intune Android compliance policy settings](https://learn.microsoft.com/en-us/mem/intune/protect/compliance-policy-create-android)
- Google의 Android Management API에서도 `SoftwareInfo.securityPatchLevel`이 device 인벤토리 신호로 존재합니다. [REST Resource: enterprises.devices](https://developers.google.com/android/management/reference/rest/v1/enterprises.devices)

운영 계약은 “무슨 CVE가 심각한가”보다 “어떤 신호로 집행할 수 있는가”를 먼저 고정해야 합니다.

## OEM 지연을 전제로 한 위험 기반 롤아웃: 11-01을 먼저 강제하는 설계

ASB는 매달 첫 번째 월요일에 게시된다고 명시되어 있습니다. 2026년 11월 공지는 실제로 11월 2일(월요일)에 게시됐습니다. [Android Security Bulletins](https://source.android.com/docs/security/bulletin/asb-overview)

또한 ASB는 여러 소스(AOSP, upstream kernel, SoC vendor)를 섞습니다. 이 사실은 “왜 11-05가 늦는가”를 운영 정책에 넣을 근거가 됩니다. [Android Security Bulletins](https://source.android.com/docs/security/bulletin/asb-overview)

이번 달 공지가 11월 6일에 “Add AOSP links”로 업데이트된 것도 운영상 힌트가 큽니다. 게시 시점(T0)에는 bulletins의 서술만 있고, 며칠 뒤(T0+4일)에 AOSP change link가 붙으면서 실제 픽업/머지/빌드가 쉬워집니다. [Android Security Bulletin—November 2026](https://source.android.com/docs/security/bulletin/2026/2026-11-01)

### 위험 기반 롤아웃에서 내가 고정하는 질문 3개

1) 11-01에 “사용자 상호작용 불필요”급이 있는가?
- 이번 달은 공지 본문이 직접 Framework Critical RCE(사용자 상호작용 불필요)를 “가장 심각한 이슈”로 지목합니다. [Android Security Bulletin—November 2026](https://source.android.com/docs/security/bulletin/2026/2026-11-01)

2) 11-05로 넘어가야만 막히는 공격면이 있는가?
- 일반적으로 kernel/vendor 영역은 11-05에 몰리고, 이쪽은 OEM 빌드 파이프라인 영향이 큽니다. 공지도 “두 패치 레벨을 둔 이유는 파트너가 공통 취약점부터 더 빠르게 고치게 하기 위함”이라고 적습니다. [Android Security Bulletin—November 2026](https://source.android.com/docs/security/bulletin/2026/2026-11-01)

3) 조직 입장에서 “지금 당장” 노출되는 플릿 구간은 어디인가?
- 업무용 단말은 MDM으로 잡을 수 있지만, BYOD/work profile은 지연과 예외가 자연스럽게 생깁니다.

이 3개를 통과하면, 정책은 보통 다음처럼 귀결됩니다.

- 11-01: 짧은 유예(예: 7일)로 전사 강제 가능
- 11-05: OEM 지연을 고려해 더 긴 유예(예: 21~45일)로 정상화 목표

여기서 중요한 것은 “유예”를 느슨함으로 해석하지 않는 것입니다. 유예는 비용 최적화 도구입니다.

- 11-01을 강하게 당기면 Framework/System 계열 리스크를 빠르게 줄일 수 있습니다.
- 11-05를 강하게 당기면 커널/베이스밴드/SoC 계열 리스크를 줄일 수 있지만, 실패율(업데이트 누락, 업무 중단)이 올라갑니다.

따라서 위험 기반 롤아웃은 보통 Ring 기반으로 갑니다.

- Ring 0: 소수 파일럿(업무 영향 측정)
- Ring 1: 고위험 직군(내부 어드민, 재무, 고객정보 접근)
- Ring 2: 일반
- Ring 3: 레거시/업무필수 예외(대신 네트워크/권한을 줄임)

이때 11-01과 11-05를 한 번에 밀어붙이면, 11-05 쪽에서 OEM/통신사 변수가 터질 때 전체 일정이 무너집니다. 나는 보통 11-01은 “보안 사고 대응”처럼 취급하고, 11-05는 “정상화 운영”으로 취급합니다.

## 플릿 운영 계약 문장: 정책은 기술이 아니라 문장으로 고정된다

운영 계약의 핵심은 “감사 가능한 문장”입니다. 공지/대시보드/코드보다 먼저 문장을 합의해야, 한 달 뒤에도 같은 방식으로 반복할 수 있습니다.

### 예시: 내가 실제로 넣는 정책 문장(골격)

1) 기준 정의
- 보안 패치 레벨은 ASB에서 정의한 `YYYY-MM-01`(partial)과 `YYYY-MM-05`(complete)로 구분한다. (정의 근거는 ASB 자체의 Q&A) [Android Security Bulletin—November 2026](https://source.android.com/docs/security/bulletin/2026/2026-11-01)
- 단말이 보고하는 SPL은 `ro.build.version.security_patch`와 동일한 날짜 문자열이다. [Android Security Bulletin—November 2026](https://source.android.com/docs/security/bulletin/2026/2026-11-01)

2) 2026-11 릴리스 요구사항
- 회사 리소스 접근 최소 요건: 2026-11-01 이상
- 정상화 요건: 2026-11-05 이상
- 단말이 2026-11-05 이상이면 2026-11 공지의 모든 이슈에 대해 “패치됨”으로 분류한다. (ASB 문구 그대로) [Android Security Bulletin—November 2026](https://source.android.com/docs/security/bulletin/2026/2026-11-01)

3) 유예와 예외
- OEM/통신사 지연은 존재하므로 2026-11-05 요구는 직군/업무 민감도에 따라 유예 기간을 다르게 둔다.
- 예외 승인 단말은 네트워크 세그먼트 분리 또는 기능 제한을 적용한다.

정책 문서에 “왜 01/05로 쪼개는가”까지 명시해 두면, 매달 반복할 때 논쟁이 줄어듭니다. ASB는 그 이유를 공식적으로 제공합니다. “파트너가 공통 취약점부터 더 빠르게 고칠 유연성을 주기 위해서”라고 말합니다. [Android Security Bulletin—November 2026](https://source.android.com/docs/security/bulletin/2026/2026-11-01)

## 단말에서 최소 보안 버전 체크하기: Build.VERSION.SECURITY_PATCH 기반 게이트

MDM이 없는 환경(또는 BYOD에서 MDM 신호가 제한적인 환경)에서는 결국 앱이 SPL을 읽어서 UX/기능을 제어해야 하는 순간이 옵니다. 앱에서 SPL을 읽는 가장 단순한 방법은 `Build.VERSION.SECURITY_PATCH`입니다. Android API reference에 “user-visible security patch level”이며 “가장 최근 보안 패치를 적용한 날짜”라고 적혀 있습니다. [Build.VERSION API reference](https://developer.android.com/reference/android/os/Build.VERSION.html)

여기서 내 결론은 단순합니다.

- 이 값은 보안의 증명이 아니라 **운영의 트리거**입니다.
- 따라서 강제 차단보다는, 기능 제한/세션 짧게/민감 작업 제한으로 연결하는 편이 실패 비용이 낮습니다.

### Android 앱 코드 (Kotlin): SPL 최소치 판정 + 서버로 posture 전송

아래 코드는 현실적인 시나리오(사내 앱이 로그인 시점에 보안 상태를 평가하고, 서버에 posture를 보내며, 서버가 민감 API를 제한)에서 바로 쓸 수 있는 형태로 작성했습니다.

#### 의존성/환경

- minSdk 23 (Android 6.0) 이상을 권장합니다. `Build.VERSION.SECURITY_PATCH`가 API 23에 추가됐습니다. [Build.VERSION API reference](https://developer.android.com/reference/android/os/Build.VERSION.html)

#### 코드

```kotlin
// SecurityPatchPolicy.kt
package com.example.posture

import android.os.Build
import java.text.ParseException
import java.text.SimpleDateFormat
import java.util.Locale

object SecurityPatchPolicy {
    private val fmt = SimpleDateFormat("yyyy-MM-dd", Locale.US)

    data class Result(
        val deviceSpl: String?,
        val requiredSpl: String,
        val isCompliant: Boolean,
        val reason: String,
    )

    /**
     * requiredSpl: 예) "2026-11-01" 또는 "2026-11-05"
     */
    fun evaluate(requiredSpl: String): Result {
        val deviceSpl = tryGetDeviceSpl()

        if (deviceSpl == null) {
            return Result(
                deviceSpl = null,
                requiredSpl = requiredSpl,
                isCompliant = false,
                reason = "device_spl_unavailable"
            )
        }

        val ok = try {
            val deviceDate = fmt.parse(deviceSpl)
            val requiredDate = fmt.parse(requiredSpl)
            deviceDate != null && requiredDate != null && !deviceDate.before(requiredDate)
        } catch (e: ParseException) {
            false
        }

        return Result(
            deviceSpl = deviceSpl,
            requiredSpl = requiredSpl,
            isCompliant = ok,
            reason = if (ok) "ok" else "device_spl_too_old"
        )
    }

    private fun tryGetDeviceSpl(): String? {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            // API 23+
            Build.VERSION.SECURITY_PATCH
        } else {
            null
        }
    }
}
```

```kotlin
// LoginViewModel.kt
package com.example.posture

import androidx.lifecycle.ViewModel

class LoginViewModel(
    private val api: PostureApi,
) : ViewModel() {

    suspend fun login(username: String, password: String) {
        // 정책: 11-01은 최소 접근 요건, 11-05는 정상화 요건
        val minAccess = SecurityPatchPolicy.evaluate(requiredSpl = "2026-11-01")
        val normalized = SecurityPatchPolicy.evaluate(requiredSpl = "2026-11-05")

        // 서버가 신뢰할 수 있게 만들려면(특히 BYOD) 이 값만 보내면 안 됩니다.
        // 그래도 운영적으로는 UX/기능 분기 트리거로 충분한 가치가 있습니다.
        api.reportPosture(
            deviceSpl = minAccess.deviceSpl,
            meetsMinAccess = minAccess.isCompliant,
            meetsNormalized = normalized.isCompliant
        )

        // 이후 로그인 진행...
        // - meetsMinAccess=false이면: 로그인은 허용하되 민감 기능 제한
        // - meetsNormalized=false이면: 경고 배너 + 민감 작업 시점에서 추가 제한
    }
}
```

#### 로컬 검증(운영팀이 현장에서 쓰는 체크)

SPL 집행이 꼬일 때, 나는 앱 로그보다 먼저 단말에서 SPL을 직접 확인합니다.

- 설정 화면의 security patch level은 결국 공지가 요구하는 문자열이어야 합니다.
- ASB도 제조사가 `ro.build.version.security_patch`를 그 문자열로 설정하라고 적습니다. [Android Security Bulletin—November 2026](https://source.android.com/docs/security/bulletin/2026/2026-11-01)

이 관점이 중요합니다. 앱이 보는 값(`Build.VERSION.SECURITY_PATCH`)과 OS property가 어긋나는 단말이 섞이면, 정책은 그 달부터 바로 깨집니다.

## 백엔드에서 최소 보안 버전 정책 집행하기: SPL은 서버에서 계약으로 완성된다

클라이언트가 SPL을 보고했다고 해서 서버가 그대로 믿으면, 그건 보안이 아니라 자기기만입니다. 따라서 백엔드 정책은 2단으로 가는 편이 낫습니다.

1) posture 신호를 수집한다(앱/MDM/attestation).
2) 기능을 단계적으로 제한한다(차단보다 downgrade).

특히 “SPL이 구버전이면 무조건 차단”은 BYOD에서 조직 내부 반발을 크게 부릅니다. 대신, 예금 이체/관리자 기능/고객정보 조회 같은 고위험 기능만 제한하는 식으로 비용을 줄이는 게 현실적입니다.

### 서버 코드 (Node.js + Express): posture 캐시 + 민감 API 게이팅

아래 예시는 인프라가 복잡하지 않은 조직에서도 바로 붙일 수 있는 형태입니다.

- 모바일 앱이 `/posture`로 SPL을 업로드
- 서버가 `/payments/high-value` 같은 민감 API에서 최소 SPL을 체크
- 정책은 11-01과 11-05를 분리해 적용

#### 실행 환경

- Node.js 20+

#### 설치/실행

```bash
mkdir posture-gateway && cd posture-gateway
npm init -y
npm i express
node server.js
```

#### 코드

```js
// server.js
const express = require('express');

const app = express();
app.use(express.json());

// in-memory cache: 실서비스라면 Redis/DB로 옮기는 게 맞습니다.
// key는 deviceId(또는 installation id)라고 가정합니다.
const posture = new Map();

function parseSpl(s) {
  // s: "YYYY-MM-DD"
  // 문자열 비교로도 동작하지만(ISO8601), 안전하게 Date로 변환합니다.
  const d = new Date(s + 'T00:00:00Z');
  if (Number.isNaN(d.getTime())) return null;
  return d;
}

function meetsSpl(deviceSpl, requiredSpl) {
  if (!deviceSpl) return false;
  const a = parseSpl(deviceSpl);
  const b = parseSpl(requiredSpl);
  if (!a || !b) return false;
  return a.getTime() >= b.getTime();
}

// 앱이 로그인 시점에 호출한다고 가정
app.post('/posture', (req, res) => {
  const { deviceId, deviceSpl } = req.body;
  if (!deviceId) return res.status(400).json({ error: 'deviceId_required' });

  posture.set(deviceId, {
    deviceSpl: deviceSpl || null,
    updatedAt: new Date().toISOString(),
  });

  res.json({ ok: true });
});

// 저위험 API: 11-01 미만이어도 제한적으로 허용
app.get('/inbox', (req, res) => {
  const deviceId = req.header('X-Device-Id');
  const p = posture.get(deviceId) || { deviceSpl: null };

  const minAccess = meetsSpl(p.deviceSpl, '2026-11-01');

  res.json({
    message: 'ok',
    deviceSpl: p.deviceSpl,
    policy: {
      minAccessRequired: '2026-11-01',
      minAccess,
    },
    // minAccess=false면 데이터 축소/마스킹 같은 전략을 적용할 수 있습니다.
  });
});

// 고위험 API: 11-05를 정상화 기준으로 강제
app.post('/payments/high-value', (req, res) => {
  const deviceId = req.header('X-Device-Id');
  const p = posture.get(deviceId) || { deviceSpl: null };

  const normalized = meetsSpl(p.deviceSpl, '2026-11-05');
  if (!normalized) {
    return res.status(426).json({
      error: 'security_patch_too_old',
      requiredSpl: '2026-11-05',
      deviceSpl: p.deviceSpl,
    });
  }

  res.json({ ok: true });
});

app.listen(3000, () => console.log('posture gateway on :3000'));
```

#### 예상 동작

```bash
# posture 업로드
curl -s -X POST localhost:3000/posture \
  -H 'content-type: application/json' \
  -d '{"deviceId":"A1","deviceSpl":"2026-11-01"}'

# 고위험 API는 11-05를 요구
curl -s -X POST localhost:3000/payments/high-value -H 'X-Device-Id: A1' | jq
# {
#   "error": "security_patch_too_old",
#   "requiredSpl": "2026-11-05",
#   "deviceSpl": "2026-11-01"
# }
```

이 구조의 장점은 “정책 문장”을 코드로 그대로 가져온다는 점입니다.

- 최소 접근 요건: 2026-11-01
- 정상화 요건: 2026-11-05

이 둘은 이번 달 ASB의 구조(01/05)와 “11-05면 모든 이슈 해결” 문구에 정확히 대응합니다. [Android Security Bulletin—November 2026](https://source.android.com/docs/security/bulletin/2026/2026-11-01)

### 클라이언트 신호를 강화하는 방법: Play Integrity의 한계와 쓰임새

SPL을 서버에서 신뢰하려면 attestation이 필요해집니다. 다만 Play Integrity는 “정확한 SPL 날짜”를 주는 도구가 아니라 “기기 신뢰 등급”을 주는 도구에 가깝습니다.

그럼에도 운영 정책에서 Play Integrity가 유용한 지점이 있습니다. Android Developers 문서에 따르면 Android 13+에서 `MEETS_STRONG_INTEGRITY`는 `MEETS_DEVICE_INTEGRITY` + 최근 1년 내 security updates(모든 partition: Android OS partition patch + vendor partition patch 포함)를 요구합니다. 즉, BYOD에서 “정확히 2026-11-05냐”를 강제하기보다 “최근 업데이트를 꾸준히 받는 기기냐”를 선별하는 데 쓸 수 있습니다. [Integrity verdicts (Play Integrity)](https://developer.android.com/google/play/integrity/verdicts)

나는 보통 이렇게 씁니다.

- 회사 소유/관리 기기: SPL을 정확 날짜로 강제(11-01/11-05)
- 비관리 기기: Strong Integrity를 만족하면 민감 기능 허용 범위를 늘리고, 만족하지 못하면 기능을 축소

이건 보안 순수주의가 아니라 운영 비용 최적화입니다.

## MDM/EMM 집행 포인트: 최소 SPL enforcement를 어디에 걸 것인가

### 1) MDM compliance: 최소 SPL을 날짜로 강제

Intune은 Android compliance policy에 Minimum security patch level을 두고, `YYYY-MM-DD` 형식으로 “이 날짜 이상이어야 compliant”라고 문서에 적습니다. [Intune Android compliance policy settings](https://learn.microsoft.com/en-us/mem/intune/protect/compliance-policy-create-android)

또 Intune의 예시 구성 문서에서는 “Android security patches는 OEM/carrier에 의존한다”는 현실을 인정합니다. 즉, 지연이 운영 변수라는 점이 문서에 이미 명시돼 있습니다. [Android Enterprise security configurations for fully managed profiles](https://learn.microsoft.com/en-us/intune/device-security/security-configurations/android-fully-managed)

BlackBerry UEM도 compliance 관점에서 security patch level을 다루며, required security patch를 만족해야 compliant로 본다고 문서에 적습니다. [BlackBerry UEM device configurations (Required security patch)](https://docs.blackberry.com/content/dam/docs-blackberry-com/release-pdfs/en/blackberry-uem/12_22/UEM-12-22-Managing-device-configurations-en.pdf)

이런 문서들이 의미하는 바는 단순합니다.

- 최소 SPL enforcement는 앱이 아니라 MDM에 두는 게 맞습니다.
- 앱은 “집행”이 아니라 “UX/단계적 제한”의 도구로 쓰는 편이 안전합니다.

### 2) Android Management API: 인벤토리 신호와 집행 분리

Google의 Android Management API에서는 `SoftwareInfo.securityPatchLevel`이 device 신호로 존재합니다. 이 값은 device 인벤토리에서 바로 뽑을 수 있는 형태입니다. [REST Resource: enterprises.devices](https://developers.google.com/android/management/reference/rest/v1/enterprises.devices)

또 “Device Trust from Android Enterprise” 쪽은 security patch level을 SYSTEM/KERNEL/SYSTEM_MODULES로 쪼개서 제공한다고 설명합니다. 신호의 granularity 자체가 SPL 하나보다 훨씬 운영 친화적입니다. [Device Trust signals (Available signals)](https://developers.google.com/android/management/device-trust-signals)

여기서 내가 내리는 판단은 다음입니다.

- 플릿 운영 계약은 여전히 11-01/11-05로 단순해야 합니다.
- 다만 내부 모니터링(왜 어떤 기기가 떨어졌는지 분석)에는 component-level 신호가 훨씬 쓸모가 큽니다.

### 3) 정책 위반 집행은 “차단/와이프”의 비용을 먼저 계산해야 한다

Android Management API 문서에는, 특정 정책 위반 시 Android Device Policy가 기본적으로 device/work profile 사용을 즉시 차단하고, 10일 후 factory reset/work profile 삭제까지 갈 수 있다고 명시합니다. 그리고 이를 `policyEnforcementRules`로 커스터마이즈할 수 있다고 설명합니다. [Set up policy compliance rules (Android Management API)](https://developers.google.com/android/management/compliance)

이 사실은 운영 계약에도 반영돼야 합니다.

- 11-01 미달을 즉시 차단으로 연결하면, 월간 공지가 “월간 장애”가 됩니다.
- 대신 11-01은 민감 리소스 접근을 줄이고, 11-05는 정상화 KPI로 두는 편이 사고 확률/운영 비용 균형이 낫습니다.

## 함정과 트레이드오프: 11-01/11-05를 계약으로 만들 때 자주 깨지는 지점

### 함정 1: SPL 문자열만으로 커널/벤더 상태를 과신한다

ASB 자체도 “두 패치 레벨이 존재한다”는 사실을 공식적으로 설명합니다. 11-01만 적용하면 11-05에 속하는 이슈는 해결되지 않는다는 뜻입니다. [Android Security Bulletin—November 2026](https://source.android.com/docs/security/bulletin/2026/2026-11-01)

또 partition 별 security patch 개념이 존재한다는 문서(AVB properties)를 보면, 운영이 정교해질수록 “system만 올렸는데 vendor는 그대로” 같은 비대칭을 의심해야 합니다. [Version information in AVB properties](https://source.android.com/docs/core/architecture/bootloader/version-info-avb)

따라서 11-05를 “완료”로 보기 전에는, 적어도 샘플링으로 이상 징후를 확인하는 절차가 필요합니다.

### 함정 2: 앱에서 읽은 SPL을 서버 정책의 증거로 쓴다

`Build.VERSION.SECURITY_PATCH`는 user-visible SPL이고 앱에서 쉽게 읽힙니다. [Build.VERSION API reference](https://developer.android.com/reference/android/os/Build.VERSION.html)

하지만 앱이 읽은 값은 조작 가능성을 완전히 제거할 수 없습니다. 그래서 서버 집행은 원칙적으로 MDM/attestation 등 **서버가 신뢰할 수 있는 채널**을 우선해야 합니다.

이런 이유로 나는 앱에서 SPL을 읽을 때도 다음 두 가지를 분리합니다.

- UX 레벨: 경고/업데이트 유도/기능 제한
- 정책 레벨: MDM compliance 결과 또는 managed device posture에 기반

### 함정 3: BYOD에서 11-05를 동일하게 강제하려고 든다

Intune 문서가 “OEM/carrier에 의존한다”고 명시하는 이유는, BYOD에서 동일 강제를 걸면 사용자 불만과 업무 중단이 폭발하기 때문입니다. [Android Enterprise security configurations for fully managed profiles](https://learn.microsoft.com/en-us/intune/device-security/security-configurations/android-fully-managed)

BYOD에는 “강제”보다 “리스크에 비례한 기능 제한”이 비용이 낮습니다. Strong Integrity 같은 등급 기반 신호를 섞으면, 최소한 “최근 업데이트를 받지 않는 단말”을 걸러내는 선별이 가능합니다. [Integrity verdicts (Play Integrity)](https://developer.android.com/google/play/integrity/verdicts)

## 도입 판단 기준: 2026-11-01/2026-11-05를 조직에 어떻게 고정할지

2026-11 공지는 2026년 11월 2일 게시 후 11월 6일 AOSP 링크가 추가되면서, 플릿 운영 정책을 문서로 고정할 근거가 충분해졌습니다. [Android Security Bulletin—November 2026](https://source.android.com/docs/security/bulletin/2026/2026-11-01)

내 기준에서 이번 달을 운영 계약으로 굳히는 결론은 다음입니다.

1) 2026-11-01을 “접근 최소치”로 선언한다.
- 이번 달 공지가 Framework의 사용자 상호작용 불필요 Critical RCE를 최상위로 지목합니다. 이런 유형은 운영적으로 11-01의 당김 근거가 됩니다. [Android Security Bulletin—November 2026](https://source.android.com/docs/security/bulletin/2026/2026-11-01)

2) 2026-11-05를 “정상화 기준”으로 선언한다.
- ASB가 “11-05 이상이 모든 이슈 해결”이라고 직접 말합니다. 이 문구는 KPI를 세우기에 충분히 강합니다. [Android Security Bulletin—November 2026](https://source.android.com/docs/security/bulletin/2026/2026-11-01)

3) 집행은 관리 단말은 MDM, 비관리 단말은 단계적 제한으로 분리한다.
- MDM은 날짜 기반 enforcement가 가능하고, 문서 근거도 충분합니다. [Intune Android compliance policy settings](https://learn.microsoft.com/en-us/mem/intune/protect/compliance-policy-create-android)
- 비관리 단말은 Strong Integrity 같은 신호를 섞어 운영 비용을 줄입니다. [Integrity verdicts (Play Integrity)](https://developer.android.com/google/play/integrity/verdicts)

4) 분쟁 포인트를 줄이기 위해 정책 문서에 “왜 01/05인가”를 적는다.
- ASB가 이유를 공식적으로 설명합니다. 파트너가 공통 취약점을 더 빨리 고치게 하기 위함입니다. [Android Security Bulletin—November 2026](https://source.android.com/docs/security/bulletin/2026/2026-11-01)

이렇게 고정하면, 매달 바뀌는 것은 CVE 목록이 아니라 “이번 달의 11-01/11-05를 언제까지 요구할지”라는 운영 숫자뿐이 됩니다. 플릿 운영은 결국 반복 작업이고, 반복 작업은 계약 문장으로만 안정화됩니다.

## 참고 자료

- [Android Security Bulletins](https://source.android.com/docs/security/bulletin/asb-overview)
- [Android Security Bulletin—November 2026](https://source.android.com/docs/security/bulletin/2026/2026-11-01)
- [Build.VERSION API reference](https://developer.android.com/reference/android/os/Build.VERSION.html)
- [Integrity verdicts (Play Integrity)](https://developer.android.com/google/play/integrity/verdicts)
- [Set up policy compliance rules (Android Management API)](https://developers.google.com/android/management/compliance)
- [REST Resource: enterprises.devices (Android Management API)](https://developers.google.com/android/management/reference/rest/v1/enterprises.devices)
- [Device Trust signals (Available signals)](https://developers.google.com/android/management/device-trust-signals)
- [Intune Android compliance policy settings](https://learn.microsoft.com/en-us/mem/intune/protect/compliance-policy-create-android)
- [Android Enterprise security configurations for fully managed profiles (Intune)](https://learn.microsoft.com/en-us/intune/device-security/security-configurations/android-fully-managed)
- [Version information in AVB properties](https://source.android.com/docs/core/architecture/bootloader/version-info-avb)
- [Android Security State Libraries](https://blog.google/security/android-security-state-libraries/)
- [Introducing the AndroidX Security State Libraries](https://developer.android.com/blog/posts/introducing-the-android-x-security-state-libraries-a-unified-view-of-device-security)
- [Understand device security state](https://developer.android.com/privacy-and-security/understand-device-security-state)
- [AndroidX Security State release notes](https://developer.android.com/jetpack/androidx/releases/security)
- [50 Shades of Support: A Device-Centric Analysis of Android Security Updates](https://www.ftc.gov/system/files/ftc_gov/pdf/16-Acar-A-Device-Centric-Analysis-of-Android-Security-Updates.pdf)
- [BlackBerry UEM device configurations (Required security patch)](https://docs.blackberry.com/content/dam/docs-blackberry-com/release-pdfs/en/blackberry-uem/12_22/UEM-12-22-Managing-device-configurations-en.pdf)

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
