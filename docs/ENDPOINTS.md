# ENDPOINTS.md — Blockman GO 1.24.4 (custom build) full API surface

> Auto-extracted from smali Retrofit annotations (`scripts/extract_endpoints.py`).
> 18 Retrofit interfaces, 213 HTTP endpoints — verified 1:1 against raw annotation counts.
> All of these must be served by the embedded loopback server (see PATCH_PLAN.md).

# Endpoint inventory (extracted from smali)

## com/sandboxol/center/web/IFriendPublicApi — 1 endpoints

| Verb | Path | Smali method |
|---|---|---|
| GET | `/friend/api/v1/friend/status/{friendId}` | `getFriendStatus` |

## com/sandboxol/center/web/IGameApi — 41 endpoints

| Verb | Path | Smali method |
|---|---|---|
| PUT | `/game/api/v1/games/{gameId}/appreciation` | `appreciation` |
| GET | `/game/api/v1/games` | `category` |
| PUT | `/game/api/v1/games/engine` | `countUploadVersion` |
| DELETE | `/game/api/v1/game/chat/room` | `deleteChatRoom` |
| POST | `/v1/follow` | `followGame` |
| GET | `/game/api/v1/flow/game/auth` | `followGameAuth` |
| GET | `/game/api/v1/games/playlist/friends` | `friendPlayList` |
| GET | `/game/api/v2/games/{gameId}` | `gameDetail` |
| GET | `/game/api/v1/games/warmup/{gameId}/languages/{language}` | `gamePreheat` |
| PUT | `/game/api/v1/game/record/ads` | `getAdsGameDouble` |
| GET | `/game/api/v1/game/{gameId}/turntable/props` | `getAdsTurnHaveReward` |
| GET | `/game/api/v1/game/{gameId}/turntable` | `getAdsTurntableInfo` |
| PUT | `/game/api/v1/game/{gameId}/turntable` | `getAdsTurntableReward` |
| GET | `/game/api/v1/games/all/open/party` | `getAllGameIdInfo` |
| GET | `/game/api/v1/games/team/member/{teamId}` | `getAuthorList` |
| POST | `/game/api/v1/game/chat/room` | `getChatRoom` |
| GET | `/game/api/v2/games/recommendation/type` | `getGameByType` |
| GET | `/shop/api/v2/shop/game/props/new` | `getGameDetailShop` |
| GET | `/game/api/v1/game/revision/list/by/condition` | `getGameListByCondition` |
| GET | `/game/api/v1/game/revision/list/recommend` | `getGameListGuessYouLike` |
| GET | `/game/api/v1/game/revision/list/more` | `getGameListMore` |
| GET | `/game/api/v1/games/{gameId}/uses/rank` | `getGameMyRank` |
| GET | `/game/api/v1/games/{gameId}/rank` | `getGameRank` |
| GET | `/game/api/v1/games/app-engine/check-update` | `getGameResource` |
| GET | `/game/api/v1/category/list/by/language` | `getGameTypeList` |
| GET | `/game/api/v1/games/update/tip/info/app/{gameId}` | `getGameUpdateContent` |
| GET | `/game/api/v1/games/update/list/{userId}` | `getGameUpdateContentList` |
| GET | `/game/api/v1/games/config/app/{gameId}` | `getPartyCreateGameConfig` |
| GET | `/v1/game-res` | `getResInfo` |
| GET | `/game/api/v1/games/stop/announcement/info` | `getStopServiceAnnouncementInfo` |
| GET | `/game/api/v1/games/announcement/info` | `getSystemAnnouncementInfo` |
| GET | `/game/api/v1/games/ugc` | `getUGCGameList` |
| GET | `/game/api/v1/games/ugc/status` | `getUGCGameStatus` |
| GET | `/game/api/v1/games/app-engine/upgrade` | `getUpgradeInfo` |
| GET | `/game/api/v1/games/{gameId}` | `miniGameDetail` |
| GET | `/v1/game-map` | `miniGameMap` |
| GET | `/game/api/v2/game/auth` | `miniGameToken` |
| POST | `/v1/dispatch` | `newMiniGameDispatcher` |
| GET | `/game/api/v1/games/playlist/recently` | `recentlyPlayList` |
| GET | `/game/api/v2/games/recommendation` | `recommendation` |
| GET | `/game/api/v1/games/resource/version` | `resCheck` |

## com/sandboxol/center/web/IScrapApi — 16 endpoints

| Verb | Path | Smali method |
|---|---|---|
| GET | `/activity/api/{version}/collect/exchange/scrap/ask` | `askScrap` |
| GET | `/activity/api/{version}/collect/exchange/user/scrap` | `getBackpackInfo` |
| GET | `/activity/api/{version}/collect/exchange/card/combine` | `getCombineNum` |
| GET | `/activity/api/v1/collect/exchange/card/details/scrap` | `getRequestTargetList` |
| GET | `/activity/api/v1/collect/exchange/reward/value` | `getRewardValue` |
| GET | `/activity/api/v1/collect/exchange/user/scrap/value` | `getScrapBagValue` |
| GET | `/activity/api/v1/collect/exchange/user/combine/record` | `getScrapCombineHistory` |
| GET | `/activity/api/v1/collect/exchange/user/scrap/{scrapId}` | `getScrapNum` |
| GET | `/activity/api/{version}/collect/exchange/card/details` | `getScrapRewardDetails` |
| GET | `/activity/api/{version}/collect/exchange/card/list` | `getScrapRewardList` |
| GET | `/activity/api/v1/collect/exchange/description` | `getScrapRule` |
| GET | `/activity/api/{version}/collect/exchange/treasurebox/timeline` | `getScrapTreasureBoxList` |
| GET | `/activity/api/v1/collect/exchange/user/vip/convert` | `getScrapVipConvert` |
| POST | `/activity/api/{version}/collect/exchange/user/combine/card` | `postCombineCardReward` |
| GET | `/activity/api/{version}/collect/exchange/scrap/receive` | `receiveScrap` |
| POST | `/activity/api/{version}/collect/exchange/scrap/send` | `sendScrap` |

## com/sandboxol/center/web/IUserApi — 80 endpoints

| Verb | Path | Smali method |
|---|---|---|
| GET | `/user/api/v1/app/auth-token` | `authToken` |
| POST | `/user/api/v1/users/secret/question` | `authUserQuestion` |
| POST | `/user/api/v1/users/bind/email` | `bindEmail` |
| POST | `/user/api/{version}/users/bind/email` | `bindEmail` |
| POST | `/user/api/v1/user/bind/phone` | `bindPhone` |
| PUT | `/user/api/v1/user/info` | `changeInfo` |
| PUT | `/user/api/v2/user/nickName` | `changeNickName` |
| GET | `/config/files/blockymods-check-version` | `checkAppVersion` |
| POST | `/user/api/v1/user/nickname/exist` | `checkNickNameTimely` |
| PUT | `/user/api/v2/users/{userId}/daily/sign/in` | `clickSignIn` |
| POST | `/user/api/v1/user/mac/id` | `countDaily` |
| POST | `/user/api/v1/user/daily/life/info` | `dailyLifeInfo` |
| GET | `/user/api/v2/users/{userId}/daily/sign/in` | `dailySignIn` |
| GET | `/config/files/indiegame-{gameId}` | `getAdsCdConfig` |
| PUT | `/user/api/v1/users/{userId}/daily/tasks/ads` | `getAdsReward` |
| GET | `/user/api/v1/users/{userId}/daily/tasks/ads/config` | `getAdsRewardInfo` |
| GET | `/user/api/v1/user/id/card/status` | `getAuthentication` |
| GET | `/user/api/v1/clan/decoration/advertising/{userId}` | `getDressAdsInfo` |
| PUT | `/user/api/v1/clan/decoration/advertising/{userId}` | `getDressAdsReward` |
| GET | `/user/api/v1/user/profile/join/switch` | `getIsShowFriendInGame` |
| GET | `/config/files/indiegame-new-{gameId}` | `getNewAdsCdConfig` |
| POST | `/user/api/v1/users/prefect/info/reward/{userId}` | `getPerfectUserInfoReward` |
| GET | `/user/api/v1/users/device/token` | `getRongToken` |
| PUT | `/user/api/v1/users/daily/sign/ads` | `getSignAdsReward` |
| GET | `/user/api/v1/videostars/config/get` | `getStarCodeConfig` |
| GET | `/user/api/v1/videostars/billing/list/get` | `getStarCodeUserIncomeDetail` |
| GET | `/user/api/v1/videostars/getbycode` | `getStarCodeUserInfo` |
| GET | `/user/api/v1/users/security/bind/email` | `getTipsEmail` |
| GET | `/user/api/v1/data/frequently/game/{userId}` | `getUserLikeGameList` |
| GET | `/user/api/v1/users/secret/question` | `getUserQuestion` |
| GET | `/user/api/v2/users/verify/user/security/settings` | `getUserVerifySettingsInfo` |
| GET | `/user/api/v1/user/player/info` | `getVipInfo` |
| GET | `/user/api/v1/user/nickName/free` | `isChangeNameFree` |
| POST | `/user/api/v1/users/prefect/info/reward/check/{userId}` | `isRewardCheck` |
| GET | `/config/files/blockmods-config-v1` | `loadAppConfig` |
| GET | `/config/files/blockymods-banner` | `loadBannerUrls` |
| GET | `/config/files/game-detail-to-editor` | `loadEditorConfig` |
| GET | `/config/files/name-sensitive-word-config` | `loadSensitiveWordConfig` |
| GET | `/config/files/blockymods-share-reward` | `loadShareReward` |
| POST | `/user/api/v1/login` | `login` |
| POST | `/user/api/v1/app/login` | `login` |
| PUT | `/user/api/v1/user/login-out` | `logout` |
| POST | `/user/api/v1/user/password/modify` | `modifyPassword` |
| GET | `/config/files/indiegame-moregame_introduction` | `moreDialogBanner` |
| GET | `/user/api/v1/users/new/daily/tasks` | `newSignInList` |
| POST | `/user/api/v1/user/id/card/status` | `postAuthentication` |
| POST | `/user/api/v1/report/push` | `postReport` |
| POST | `/user/api/v1/user/language` | `postUserLanguage` |
| PUT | `/user/api/v1/videostars/cashapply` | `putCashApply` |
| PUT | `/user/api/v1/videostars/exchange` | `putCashExchange` |
| POST | `/user/api/v1/register` | `register` |
| POST | `/user/api/v1/app/renew` | `renew` |
| POST | `/user/api/v1/app/renew` | `renew` |
| POST | `/user/api/v1/report/status` | `reportStatus` |
| POST | `/user/api/v1/emails/password/reset` | `resetPassword` |
| POST | `/user/api/v1/users/question/reset/password` | `resetPasswordBySecretQuestion` |
| POST | `/user/api/v1/sms/send/refound` | `retrieve` |
| POST | `/user/api/v1/user/password` | `retrievePassword` |
| POST | `/user/api/v1/sms/send/{phone}` | `sendCode` |
| POST | `/user/api/v1/emails/{email}` | `sendEmailCode` |
| POST | `/user/api/v1/emails/verify/{email}` | `sendEmailVerifyCode` |
| POST | `/user/api/v1/users/security/verify/email/reset` | `sendFullEmailToVerify` |
| POST | `/user/api/v1/user/profile/join/switch` | `setIsShowFriendInGame` |
| POST | `/user/api/v1/app/set-password` | `setPassword` |
| POST | `/user/api/{version}/users/secret/question/setting` | `setUserQuestion` |
| POST | `/user/api/v1/users/sharing/reward` | `shareReward` |
| PUT | `/user/api/v1/users/tasks/{type}` | `signIn` |
| GET | `/user/api/v1/users/dairy/tasks/{type}` | `signInList` |
| DELETE | `/user/api/v1/users/{userId}/emails` | `unbindEmail` |
| DELETE | `/user/api/v2/users/{userId}/emails` | `unbindEmail` |
| POST | `/user/api/v1/user/unbind/phone` | `unbindPhone` |
| POST | `/user/api/v1/users/unbind/user/security` | `unbindUserSecretQuestion` |
| POST | `/user/api/v1/user/details/info` | `updateUserInfo` |
| PUT | `/user/api/v1/user/device/id` | `uploadDeviceId` |
| POST | `/user/api/v1/user/mac/id` | `uploadID` |
| POST | `/user/api/v1/file` | `uploadIcon` |
| POST | `/user/api/v1/user/register` | `userRegister` |
| POST | `/user/api/v1/users/verify/email` | `verifyEmail` |
| POST | `/user/api/v1/users/security/verify/email` | `verifyEmailBeforeSetSecretQuestion` |
| POST | `/user/api/v1/visitor` | `visitor` |

## com/sandboxol/center/web/IVipApi — 1 endpoints

| Verb | Path | Smali method |
|---|---|---|
| GET | `/pay/api/v1/sub/info/get` | `getSubscribeInfo` |

## com/sandboxol/decorate/web/IDecorationApi — 17 endpoints

| Verb | Path | Smali method |
|---|---|---|
| GET | `/decoration/api/v1/new/decorations/check/resource` | `checkDressResource` |
| GET | `/decoration/api/{version}/decorations/{typeId}` | `dressList` |
| GET | `/decoration/api/v1/decorations/{otherId}/using` | `friendUsingList` |
| GET | `/decoration/api/v1/new/decorations/users/{userId}/expire` | `getDressInfoExpireList` |
| GET | `/decoration/api/v1/new/decorations/users/{userId}/type/{typeId}` | `getDressListByType` |
| GET | `/decoration/api/v1/new/decorations/users/{userId}/suit` | `getDressSuitList` |
| GET | `/decoration/api/v1/new/decorations/recommend/users/{userId}/type/{typeId}` | `getRecommendList` |
| GET | `/decoration/api/v1/decorations/using` | `isUsingList` |
| GET | `/config/files/dress-guide-config` | `loadDressGuideConfig` |
| PUT | `/decoration/api/v1/decorations/using/new` | `multiClothe` |
| DELETE | `/decoration/api/v1/decorations/using/new` | `multiUnclothe` |
| DELETE | `/decoration/api/v1/decorations/using/{decorationId}` | `removeDecoration` |
| DELETE | `/decoration/api/v1/decorations/using` | `removeSuitDecoration` |
| GET | `/decoration/api/v1/decoration/versions` | `resCheck` |
| PUT | `/decoration/api/v1/decorations/using/{decorationId}` | `useDecoration` |
| PUT | `/decoration/api/v1/decorations/using` | `useSuitDecoration` |
| GET | `/decoration/api/v1/vip/decorations/users/{typeId}` | `vipDress` |

## com/sandboxol/decorate/web/IShopApi — 14 endpoints

| Verb | Path | Smali method |
|---|---|---|
| PUT | `/shop/api/v1/shop/decorations/buy/{decorationId}` | `buy` |
| PUT | `/shop/api/v1/shop/decorations/buy` | `buy` |
| POST | `/shop/api/v1/new/shop/decorations/buy` | `buyByV2` |
| GET | `/shop/api/v1/shop/decorations/details/{decorationId}` | `changeDecoration` |
| GET | `/shop/api/v1/new/shop/suit/info/{suitId}` | `getDressSuit` |
| GET | `/shop/api/v1/new/shop/suit/list/info` | `getSuitById` |
| POST | `/shop/api/v1/new/shop/gift/suit/receive` | `getSuitGift` |
| GET | `/shop/api/v1/new/shop/gift/suit/receive` | `getSuitGiftId` |
| GET | `/shop/api/v1/new/shop/user/gift/suit/receive` | `isCanReceiveGiftSuit` |
| GET | `/shop/api/v1/shop/decorations/recommends/{decorationId}` | `recommendList` |
| GET | `/shop/api/{version}/shop/decorations/{typeId}` | `shopList` |
| GET | `/shop/api/v1/new/shop/decorations/{typeId}` | `shopListByV2` |
| GET | `/shop/api/v1/new/shop/recommend/decorations` | `shopRecommendByV2` |
| GET | `/shop/api/v1/new/shop/suit/decorations` | `shopSuitByV2` |

## com/sandboxol/gameblocky/web/IBlockyGameApi — 5 endpoints

| Verb | Path | Smali method |
|---|---|---|
| POST | `/v1/follow` | `followGame` |
| GET | `/game/api/v1/flow/game/auth` | `followGameAuth` |
| GET | `/v1/game-map` | `miniGameMap` |
| GET | `/game/api/v2/game/auth` | `miniGameToken` |
| POST | `/v1/dispatch` | `newMiniGameDispatcher` |

## com/sandboxol/gameblocky/web/IBlockyUserApi — 1 endpoints

| Verb | Path | Smali method |
|---|---|---|
| POST | `/user/api/{version}/directory/file` | `uploadFile` |

## com/sandboxol/gameblocky/web/IShopApi — 2 endpoints

| Verb | Path | Smali method |
|---|---|---|
| PUT | `/shop/api/v1/shop/decorations/buy/{decorationId}` | `buy` |
| POST | `/shop/api/v1/new/shop/decorations/buy` | `buyByV2` |

## com/sandboxol/gamedetail/web/IGameDetailsApi — 2 endpoints

| Verb | Path | Smali method |
|---|---|---|
| PUT | `/shop/api/v2/pay/game/{gameId}` | `bugGame` |
| PUT | `/shop/api/v3/shop/game/props/new` | `buyGameDetailShopGoods` |

## com/sandboxol/googlepay/billing/IPayApi — 16 endpoints

| Verb | Path | Smali method |
|---|---|---|
| POST | `/pay/api/v4/pay/users/recharge` | `buySubs` |
| POST | `/pay/api/v3/pay/users/recharge` | `buyVip` |
| POST | `/pay/api/v4/pay/users/recharge` | `buyVipExtend` |
| GET | `/pay/api/v1/first/punch/reward` | `firstTopReward` |
| GET | `/pay/api/v1/pay/payssion/signature` | `getPaySignature` |
| GET | `/pay/api/v1/pay/payssion/flag` | `isShowThirdPart` |
| GET | `/pay/api/v1/pay/third/part` | `isShowThirdPartPay` |
| GET | `/pay/api/v1/pay/products` | `productsList` |
| POST | `/pay/api/v2/pay/users/recharge` | `recharge` |
| POST | `/pay/api/v2/pay/users/recharge` | `recharge` |
| POST | `/pay/api/v1/pay/users/recharge` | `rechargeGift` |
| GET | `/pay/api/v1/wealth/record/users/{userId}` | `rechargeHistory` |
| GET | `/pay/api/v2/pay/third/part` | `showThirdPartPayList` |
| GET | `/pay/api/v1/wealth/user` | `updateMoney` |
| GET | `/pay/api/v1/pay/products/vip` | `vipProductsList` |
| GET | `/pay/api/v2/pay/products/vip` | `vipSubsProductsList` |

## com/sandboxol/halloween/web/IHalloweenApi — 6 endpoints

| Verb | Path | Smali method |
|---|---|---|
| POST | `/activity/api/v1/halloween/candy/exchange` | `exchangeCandy` |
| POST | `/activity/api/v1/halloween/reward/exchange` | `exchangeReward` |
| GET | `/activity/api/v1/halloween/info` | `getDetailInfo` |
| GET | `/activity/api/v1/halloween/task/info` | `getTaskList` |
| GET | `/decoration/api/v1/decorations/using` | `isUsingList` |
| POST | `/activity/api/v1/halloween/task/reward/receive` | `receiveTaskReward` |

## com/sandboxol/imchat/web/IChatGameApi — 1 endpoints

| Verb | Path | Smali method |
|---|---|---|
| GET | `/game/api/v2/party/auth` | `getPartyAuth` |

## com/sandboxol/imchat/web/IPartyApi — 1 endpoints

| Verb | Path | Smali method |
|---|---|---|
| GET | `/api/v1/parties/exists` | `isPartyExist` |

## com/sandboxol/pingreport/web/IPingReportApi — 1 endpoints

| Verb | Path | Smali method |
|---|---|---|
| POST | `/datareport/api/v1/app/ping/report/batch` | `reportPingEvent` |

## com/sandboxol/report/web/IReportInfoApi — 2 endpoints

| Verb | Path | Smali method |
|---|---|---|
| POST | `/datareport/api/v1/funnel/event/report` | `newReportSandboxData` |
| POST | `/datareport/api/v1/event/report` | `reportSandboxData` |

## com/sandboxol/videosubmit/web/IVideoSubmitApi — 6 endpoints

| Verb | Path | Smali method |
|---|---|---|
| GET | `/config/files/bg-tube-activity-config` | `getBGTubeConfigInfo` |
| GET | `/activity/api/v1/bgtube/multilingualism/info` | `getBGTubeMultiLanguageConfig` |
| GET | `/activity/api/v1/bgtube/sign` | `getBGTubeSignInfoResponse` |
| GET | `/activity/api/v1/bgtube/sign/check` | `getSignUpStatus` |
| POST | `/activity/api/v1/bgtube/sign` | `postSignUp` |
| POST | `/activity/api/v1/bgtube/video/link` | `postVideoLink` |


# Implementation status (embedded local API server)

The embedded server (localapi-server/, NanoHTTPD on 127.0.0.1:18080) serves all
321 routes. State-backed handlers return real, persistent, dynamically
generated data; everything else answers a schema-true default so Gson models
never crash (list endpoints return [], obj endpoints return {} — matching the
HttpResponse envelope {code:1, message, data}).

## State-backed handlers (Phase 1 + Phase 2)

| Route | Handler | Behavior / state |
|---|---|---|
| POST /user/api/v1/login (+/app/login, v2) | login | password check, per-user token, wallet, isFirstLogin |
| POST /user/api/v1/register | register | new account, unique-uid check, token |
| POST /user/api/v1/user/register | userRegister | role-make: nickName/sex onto authed user |
| POST /user/api/v1/visitor | visitor | stable per-imei visitor + Visitor{id, accessToken, nickName} |
| POST /user/api/v1/app/user/tourist/login | tourist | stable per-device guest |
| GET /user/api/v1/app/auth-token | authToken | fresh token, hasPassword, hasBinding |
| POST /user/api/v1/app/renew | renew | same as auth-token |
| PUT /user/api/v1/user/login-out | logout | drops token |
| GET /user/api/v1/users/device/token | rongToken | HttpResponse<String> chat token |
| PUT /user/api/v2/user/nickName | changeNickName | persists nickName |
| PUT /user/api/v1/user/info + POST details/info | changeInfo | nickName/sex/details/birthday/picUrl |
| GET /config/files/blockymods-check-version | checkVersion | no-update (newVersionCode 4003) |
| GET /config/files/blockmods-config-v1 | appConfig | all external content off |
| GET /game/api/v1/games | category | PageData<Game> — filter by typeId, sort by orderType/order |
| GET /game/api/v1/game/revision/list/by/condition | gameListByCondition | TypePageData<Game> — sortType (online/new/appreciate/complex) + filterTypeId + paging |
| GET /game/api/v1/game/revision/list/more | gameListMore | PageData<Game> |
| GET /game/api/v1/game/revision/list/recommend | gameListGuessYouLike | List<Game> top-praised |
| GET /game/api/v2/games/recommendation | recommendation | List<Game> top-online |
| GET /game/api/v2/games/recommendation/type | getGameByType | PageData<Game> by category name/sortType |
| GET /game/api/v1/games/ugc | getUGCGameList | PageData<Game> isUgcGame=1 |
| GET /game/api/v1/games/playlist/recently | recentlyPlayList | per-user played history (state; empty until Phase 4 dispatch records plays) |
| GET /game/api/v1/games/playlist/friends | friendPlayList | [] (no friends yet — real empty state) |
| GET /game/api/v1/games/{gameId} + v2 | miniGameDetail / gameDetail | full Game model or code=0 "game not found" |
| GET /game/api/v1/games/warmup/{gameId}/languages/{lang} | gamePreheat | GameWarmUpResponse from catalog |
| GET /game/api/v1/category/list/by/language | getGameTypeList | 6 generated categories {typeId,typeName,sortType} |
| GET /game/api/v1/games/announcement/info (+stop) | announcements | isShow=false |
| GET /game/api/v1/games/all/open/party | getAllGameIdInfo | List<AllGameIdInfo> from isOpenParty=1 games |
| GET /game/api/v1/games/{gameId}/rank | getGameRank | RankInfo{pageInfo: rank rows, remainTime} — persistent boards |
| GET /game/api/v1/games/{gameId}/uses/rank | getGameMyRank | requesting user's CampaignRank |
| GET /shop/api/v2/shop/game/props/new | getGameDetailShop | persistent per-game prop list (generated once) |
| GET /game/api/v1/games/config/app/{gameId} | getPartyCreateGameConfig | member limits |
| POST /game/api/v1/game/chat/room | getChatRoom | persistent roomId per roomName |
| PUT /game/api/v1/games/{gameId}/appreciation | appreciation | increments praiseNumber, returns new total |
| GET /game/api/v2/game/auth (+/flow/game/auth, /v1/game-map) | miniGameToken | dynamic token issued into root.miniTokens; dispUrl=http://127.0.0.1:18080 (this server); requestId {uid:hex} |
| GET /v1/game-res | gameResInfo | GameResInfo with the loopback CDN as base source + query resVersion echo |
| GET /game/api/v1/games/resource/version | resCheck | {update:false} |
| GET /game/api/v1/games/app-engine/upgrade | getUpgradeInfo | {needUpgrade:false} |
| GET /game/api/v1/games/app-engine/check-update | getGameResource | [] (nothing to update) |
| PUT /game/api/v1/games/engine | countUploadVersion | engine-version telemetry recorded into root.engineReports (last 20 kept), ack |
| GET /user/api/v2/users/{userId}/daily/sign/in | dailySignIn | Map first..seventh DailySignInfo; status semantics are the CLIENT's (j/h.java): 0 = "It isn't time to sign in" (future), 1 = claimable today, 2 = "Received"; Xb.onSuccess opens WeekSignDialog only when some day is 1 |
| PUT /user/api/v2/users/{userId}/daily/sign/in | clickSignIn | claims today's slot, credits 200..3000 golds (7-day cycle) |
| PUT /user/api/v1/users/{userId}/daily/tasks/ads | getAdsReward | +200 golds (cap 5/day), RechargeEntity |
| PUT /user/api/v1/users/daily/sign/ads | getSignAdsReward | +300 golds (cap 3/day), AdsSignReward |
| GET /user/api/v1/users/{userId}/daily/tasks/ads/config | getAdsRewardInfo | {currency:1, quantity:200} |
| GET /friend/api/v1/friends (+requests, follow) | friend pages | valid empty PageData (fresh account) |
| GET /friend/api/v1/friends/recommendation[/new] | friendRecommendation | real accounts + persistent citizens pool |
| GET /user/api/v1/user/player/info | getVipInfo | BuyVipEntity {vip, gDiamonds} |
| GET /pay/api/v1/sub/info/get | getSubscribeInfo | VipSubInfo {playerInfo, subInfo:[]} |

## Generated catalog (dynamic, persisted in state.json)

On first boot the server generates and PERSISTS: 6 categories, 42 games
(generated names/attributes, ids 5001+, mix of UGC/party/shop flags), 36
citizen players (rank boards + friend recommendations), per-game prop shops,
per-game rank boards. onlineNumber drifts per boot hour. Nothing is hardcoded
per-request; after generation the catalog is ordinary editable server state.
Delete state.json to regenerate.

## Known limitations / uncertainty (documented, not assumed)

- DailySignInfo.status semantics (claimed vs unclaimed) are inferred; UI cosmetics only.
- Currency mapping VERIFIED from client code (three independent sites): 1=diamonds, 2=golds — the recharge reward dialog shows ic_diamond for currency 1 (googlepay/recharge/r.java), the game-detail buy flow checks currency!=2 price against the diamonds balance (gamedetail GameDetailShopItemViewModel), and the dress checkout sums the currency!=2 bucket against the diamonds wallet (decorate E.java). All local economy handlers (dress/suit buy, recharge products, ads rewards, prop buy) follow this mapping.
- gameId is a String in the client model — catalog ids are numeric strings.
- Game join/dispatch (POST /v1/dispatch, Dispatch model) returns the final API
  shape with gaddr=127.0.0.1:18080 (host:port — the client split(":") it). The
  Engine 10068 GameServer itself is a later project phase; today the engine
  would connect to the loopback API endpoint. Nothing about the contract is
  faked: tokens are issued/validated against real state (root.miniTokens).

## Phase 3 handlers (this session, decoration + dress shop + scrap)

| Route | Handler | Behavior |
|---|---|---|
| GET /decoration/api/{version}/decorations/{typeId} | dressList | per-type catalog, generated once + persisted (10 items/type) |
| GET /decoration/api/v1/new/decorations/users/{userId}/type/{typeId} | dressOwnedByType | user's owned dresses of that type (wardrobe state) |
| GET /decoration/api/v1/decorations/using | isUsingList | worn dresses (own via token, others via otherId) |
| GET /decoration/api/v1/decorations/{otherId}/using | friendUsingList | another player's worn dresses |
| PUT /decoration/api/v1/decorations/using/{decorationId} | useDecoration | wear (must be owned) |
| PUT /decoration/api/v1/decorations/using/new?ids= | multiClothe | wear many |
| PUT /decoration/api/v1/decorations/using?ids= | useSuitDecoration | wear list (ownership checked) |
| DELETE /decoration/api/v1/decorations/using/{decorationId} | removeDecoration | unwear one |
| DELETE /decoration/api/v1/decorations/using?ids= | removeSuitDecoration | unwear list |
| DELETE /decoration/api/v1/decorations/using/new?ids= | multiUnclothe | unwear list |
| PUT /shop/api/v1/shop/decorations/buy/{decorationId} | dressBuyOne | real purchase: wallet deduction + ownership |
| PUT /shop/api/v1/shop/decorations/buy?decorationId=a,b | dressBuyMany | BuyDressResponse w/ per-id status |
| POST /shop/api/v1/new/shop/decorations/buy | dressBuyV2 | BuyRequest{buyDecorationList[{decorationId}]} |
| GET /shop/api/v1/shop/decorations/details/{decorationId} | dressDetails | SingleDressInfo |
| GET /shop/api/v1/shop/decorations/recommends/{decorationId} | dressRecommendList | same-type suggestions |
| GET /shop/api/{version}/shop/decorations/{typeId} + v1/new/... | shopList | same generated catalog |
| GET /shop/api/v1/new/shop/recommend/decorations | shopRecommendV2 | ShopRecommendDecorationInfo rows |
| GET /shop/api/v1/new/shop/user/gift/suit/receive | giftSuitCanReceive | true until the one-time gift suit is claimed (per-user state) |
| GET /config/files/dress-guide-config | dressGuideConfig | empty map |
| GET /decoration/api/v1/decoration/versions + new/.../check/resource | res checks | no update |
| GET /activity/api/{version}/collect/exchange/user/scrap | scrapBackpack | 6 scrap types generated per user, amounts persist |
| GET /activity/api/v1/collect/exchange/user/scrap/{scrapId} | scrapNum | from backpack |
| GET /activity/api/v1/collect/exchange/user/scrap/value | scrapBagValue | sum of values |
| GET /activity/api/{version}/collect/exchange/card/list | scrapCardList | 6 cards (generated) |
| GET /activity/api/{version}/collect/exchange/card/details | scrapCardDetails | card -> required scraps |
| POST /activity/api/{version}/collect/exchange/user/combine/card | scrapCombineCard | consumes scraps, credits golds, records history |
| GET /activity/api/v1/collect/exchange/user/combine/record | scrapHistory | persistent history |
| GET /activity/api/v1/collect/exchange/card/details/scrap | scrapRequestTargets | citizens as helpers |
| GET /activity/api/v1/collect/exchange/description | scrapRule | rules text |
| POST /activity/api/{version}/collect/exchange/scrap/send | scrapSend | consumes 1 scrap, returns uuid |
| GET .../scrap/ask + scrap/receive + treasurebox + vip/convert + reward/value + card/combine | simple state | acks/constants |

## Phase 5 handlers (dispatch bridge + suits + file upload)

| Route | Handler | Behavior |
|---|---|---|
| POST /v1/dispatch | dispatch | validates x-shahe-uid/x-shahe-token against root.miniTokens; returns the full Dispatch model (gaddr host:port, croomid persistent chat room, mid/mname, requestIds, resVersion echo, signature/timestamp from the token) |
| POST /v1/follow | follow | same Dispatch shape for followed games |
| GET /v1/game-res | gameResInfo | GameResInfo{cdns:[local base cdn], durl, resVersion} |
| PUT /game/api/v1/game/record/ads | recordAdsGame | credits 100 golds (shared 5/day ad cap), returns the amount |
| GET /shop/api/v1/new/shop/suit/decorations | shopSuitList | 6 persisted suits (root.suits) bundling real dress ids, SuitDressInfo shape |
| GET /shop/api/v1/new/shop/suit/list/info?suitIds= | suitListByIds | filtered suit list |
| GET /shop/api/v1/new/shop/suit/info/{suitId} | suitDetail | one suit with component SingleDressInfo lists |
| GET /shop/api/v1/new/shop/gift/suit/receive | suitGiftInfo | the giftable suit (or {} once claimed) |
| POST /shop/api/v1/new/shop/gift/suit/receive?suitId= | suitGiftReceive | one-time claim: marks suit + component dresses owned, returns the dresses |
| GET /shop/api/v1/new/shop/user/gift/suit/receive | giftSuitCanReceive | real per-user gift state |
| GET /decoration/api/v1/new/decorations/users/{userId}/suit | dressSuitList | owned suits (real wardrobe state) |
| POST /shop/api/v1/new/shop/decorations/buy | dressBuyV2 (extended) | handles BuyRequest.buySuitList: wallet math + suitPurchaseStatus + component dresses owned |
| POST /user/api/v1/file | uploadFile | @Multipart uploadIcon: parses the file part, stores bytes under localapi/files/<id>, returns http://127.0.0.1:18080/files/<id> |
| POST /user/api/{version}/directory/file | uploadFile | same for IBlockyUserApi.uploadFile |
| GET /files/<id> (server extension) | file serving | returns stored upload bytes with the stored mime type (this route is our own; the client fetches it as a plain URL, not Retrofit) |
| GET /config/files/name-sensitive-word-config | sensitiveWords | persisted local sensitive-word list; nickNameExist filters against it for real |


## Phase 5b handlers (geoinfo + region ranking + party auth)

| Route | Handler | Behavior |
|---|---|---|
| POST /geoinfo/api/v1/userGeoInfo?longitude=&latitude= | postUserGeoInfo | stores the user's real coordinates in user state (strict auth) |
| GET /geoinfo/api/v1/userGeoInfo | userGeoList | UserMapInfo list: requester (if geo posted) + citizens with lazy persisted coordinates; x/y equirectangular projection, distance = km (haversine) from the requester |
| GET /geoinfo/api/v1/user/game/career/data/{userId} | careerData | UserGameCareerTotalData with truthful zero counters (no engine sessions yet) + gameTimeMap keys from the real played history |
| GET /ranking/api/v1/ranking/region/home/page/info?rankType= | regionRankHome | RankHomePageInfoResponse: podium = ONE row per category (type = gDiamond/active/clan, each the #1 of that board across users+citizens) — client contract overviewrank/f.java maps row type -> rank template and ANY other value makes the tap a silent no-op; remainingTime = ms to next Monday UTC |
| GET /ranking/api/v1/ranking/user/info?rankType=&type=&isRegion= | userRankInfo | the requesting user's RankInfoResponse (rank + quantity from real state; types gold/gDiamond/clan/active) |
| GET /game/api/v2/party/auth | partyAuth | PartyAuthInfo shape with partyService=127.0.0.1:18080 (host:port — the client split(":") it) + dynamic token/signature; the gRPC party transport stays offline (RongCloud-shim policy) |
| GET /api/v1/parties/exists | partiesExists | "" (no party exists in the local world) |


## Phase 5c handlers (real mailbox + engine telemetry)

Client semantics verified from jadx (IMailBoxApi, InboxModel j/g/h/i,
InboxDetailViewModel k): MailInfo{id, title, content, type, extra, sendDate,
status, attachment:[{type,itemId,name,icon,qty}]}; status 0=unread, 2=read
(opening a mail marks it read via mailOperation(2, ids)), 3=delete request
("delete read" collects status==2 rows and sends mailOperation(3, ids));
hasNewEmail drives the unread badge; attachment claim renders the reward
dialog from the local copy and moves the mail to read.

| Route | Handler | Behavior |
|---|---|---|
| GET /mailbox/api/v1/mail | mailList | the user's mails, newest first (strict auth) |
| GET /mailbox/api/v1/mail/new | hasNewEmail | true when any mail has status 0 (strict auth) |
| PUT /mailbox/api/v1/mail?status=&ids= | mailOp | 2=mark read, 3=delete; returns the updated mail list |
| PUT /mailbox/api/v1/mail/attachment?mailId= | mailAttachment | claims attachments into the wallet once (type 1=diamonds, 2=golds — the local currency ids), marks read, rejects re-claim |
| PUT /game/api/v1/games/engine | countUploadVersion | engine-version telemetry recorded into root.engineReports (last 20 kept) |

Every NEW account (register / visitor / tourist paths) receives a one-time
welcome mail (500 golds attachment) guarded by a per-user flag — deleting the
mail never re-issues it. Mail state persists in state.json like the rest of
the world; host rig asserts the no-re-credit guarantee across a restart.

## Phase 5d handlers (game-detail prop shop buy + currency correction)

| Route | Handler | Behavior |
|---|---|---|
| PUT /shop/api/v3/shop/game/props/new?gameId=&propsId= | buyGameProp | buys a prop from the game's detail shop: strict auth, wallet deduction (currency 1=diamonds, 2=golds), one-time ownership per user (userState.ownedProps), re-buy rejected |

PUT /shop/api/v2/pay/game/{gameId} stays a default: every generated game has
isPay=0 ("quick enter"), so the client never pays to play — the default is
the honest state, not a gap.

The turntable (GET/PUT /game/api/v1/game/{gameId}/turntable[/props]) also
stays default BY DECISION: an empty wheel list keeps AdsTurntableDialog from
opening, and its spin is triggered by the ad-watch completion message —
ads do not exist in the local world. Implementing the list would surface a
dialog that can never spin.

GET /config/files/blockymods-share-reward is now real (shareRewardList): one
row {id:1, picUrl:"", count:200} — exactly what POST sharing/reward grants
(200 golds once per day). The client binds picUrl→icon and count→label.

## Phase 5f handlers (chat-room lifecycle + deep-drive discovery wave)

| Route | Handler | Behavior |
|---|---|---|
| DELETE /game/api/v1/game/chat/room?roomId= | deleteChatRoom | drops the name→roomId binding for the room the client left (idempotent: unknown ids answer ok); a later POST for the same room name issues a fresh persistent id |

POST /game/api/v1/game/chat/room keeps issuing stable persistent ids per
roomName; DELETE now makes the lifecycle symmetric (leave = forget).

Config-shape pass evaluated, NOT implemented (deliberate): the remaining
`obj` defaults (`indiegame-{gameId}`/`indiegame-new-{gameId}` AdsCdConfig,
`game-detail-to-editor` Map, `blockymods-activity-logo` CampaignLogo) would
parse from `data:{}` to identical Gson outcomes as any honest empty value —
zero client-observable change — so no handler was added. Shapes are recorded
here from jadx: AdsCdConfig{adsCdTimeFirst:int, adsCdTimeSecond:int};
game-detail-to-editor: Map<String,List<String>>; CampaignLogo{normalLogo,
redPointLogo}; banner rows BannerEntity{id, image, isFullScreen, isInside,
isTest, title, titles:Map<String,String>, url, version, videoId,
countryList}; moregame rows BannerInfo{image, packageName, title}.

Deep-drive discovery: the redroid UI automation now visits the Inbox / Top Up
/ Ranking rows of the Me tab and taps a Home game card (labels verified from
the on-device uiautomator dump), printing which endpoint paths the newly
visited screens add. A crash on any driven screen fails CI (real finding).

## Phase 5g handlers (video feed — on-device crash fix)

The v0.5.6 deep drive probed the Video row and the client CRASHED on-device:
`BaseVideoInfoDbHelper` NPE (null List iterator) — the video screen caches
`pageData.getData()` into greendao, and a bare `data:[]` parses into a
PageData whose list is null. Client-first fix, exact shapes from
IVideoApi + PageData (flat: data/pageNo/pageSize/totalPage/totalSize):

| Route | Handler | Behavior |
|---|---|---|
| GET /video/api/v1/app/video/list/{type} | videoPageList | real flat PageData with data:[] (empty list, totalPage 0 — pager stops) |
| GET /video/api/v1/app/video/more/list | videoPageList | same PageData shape |
| GET /video/api/v1/app/video/tag/list | videoTagList | {} (no video tags locally) |
| GET /video/api/v1/app/video/detail/info | videoDetailInfo | data absent (no videos exist) |
| POST /video/api/v1/app/video/praise/{videoId} | videoFeedback | 0 (honest ack, no videos) |
| POST /video/api/v1/app/video/dislike/{videoId} | videoFeedback | 0 |
| POST /video/api/v1/app/video/report/play/amount | videoPlayAck | 0 |

Deliberate: no videos are fabricated locally (no video content exists to
serve); the fix is purely the response SHAPE so the screen shows its empty
state instead of crashing.

## Phase 5i (profile-edit path driven through the real UI)

No new handlers and no behavior change on the server — this wave made the
automation drive, for the first time, the profile-edit surface end-to-end:

| Route (already implemented) | Handler | UI surface |
|---|---|---|
| PUT /user/api/v2/user/nickName | changeNickName | Personal Info editor -> Nickname row (deterministic: typed, saved, row-refresh verified) |
| POST /user/api/v1/user/nickname/exist | nickNameExist | fired by the client during the nickname edit |
| POST /user/api/v1/user/details/info | changeInfo | Personal Info editor -> Gender row (best-effort) |
| PUT /user/api/v1/user/info | changeInfo | same editor (alternate change path) |

Phase B of scripts/ui_automation_test.py was reworked: it no longer taps the
Me-tab account row (ll_account) — that guest register-upgrade Tip's teardown
is the NATIVE killer (Session 11 forensics) and the UI register never once
completed. Instead Phase B drives the Personal Info editor (Profile -> ibMore
-> Nickname/Gender rows) and asserts the profile-edit endpoints hit the local
server. A guest-Tip detector aborts the drive immediately if the app ever
guest-gates an editor row (the killer must not be fed). Account creation
remains owned by Phase C (fresh account every run through the real server).

## Phase 5i final (session 12 verified green — v0.5.19-clientfix)

The full registered-session profile-edit chain is now exercised through the
REAL client on-device (test-redroid PASS, 63 unique endpoints, zero
crashes):

| Step | Surface | Verification |
|---|---|---|
| Guest rename attempt (Phase B) | ChangeNameFragment + GET /user/api/v1/user/nickName/free | the client's native guest gate fires (kick); PUT never allowed — documented client behavior |
| Session upgrade (Phase D) | GET /user/api/v1/app/auth-token?userId= + POST /user/api/v2/app/set-password | the live Me-tab user id is upgraded; login with the new credentials returns the same userId |
| Registered restart (Phase D) | boot restores the saved session | the Me tab shows the new account name on-device |
| Registered rename (Phase D) | PUT /user/api/v2/user/nickName?newName=&oldName= | handler fixed for the client contract (was a silent no-op); server state proven via nickname/exist -> taken |

Two real server bugs were exposed by the real client and fixed this wave
(host rig 337/337 incl. 4 new client-contract regressions):
1. changeNickName read `nickName=` while the client sends `newName=`.
2. login could not resolve guests upgraded via set-password (findByAccount
   added).

# Error-code contract (Phase 7 — client-verified)

The embedded server no longer returns a bare `code:0` for domain errors.
Every requireUser failure returns code 7; user/tribe/friend/group error
paths return the exact codes the 1.24.4 client's OnError mappers translate
into toasts (101/102/7012/7020 user; 5006/5007/7001-7006/7008/7011/7012/
7014/7020 tribe; 3001-3004 friend; 8102/8103/8104 group chat). The full
evidence table + the decompiled gate analysis live in PATCH_PLAN.md
"Phase 7"; constants in localapi-server ErrorCodes.java. Unknown/legacy
messages still fall back to code 0 (client shows the generic server-error
toast) — documented-deliberate.

### Phase F2 addition (Session 17)

PUT /clan/api/v1/clan/tribe (clanUpdate) now carries the same domain
rules as create: renaming onto an existing clan name returns 7002
(tribe_name_exist — the client's edit form has no uniqueness gate, the
server owns the rule; evidence chain in PATCH_PLAN "Phase F2"), a
non-member PUT returns 7006 (tribe_not_joined), chief-only stays 7003.
The route itself was already a real handler; the on-device UI drive
(Phase F2) client-asserts it end-to-end.

# Wave 5v (Session 19): campaign sign-in + datareport sink + turntable status

## New state-backed handlers (client-contract decoded, host-rig proven)

| Route | Handler | Client evidence (jadx) |
|---|---|---|
| GET /activity/api/v1/signIn | campaignSignInList | ICampaignApi.signInList -> UserSignInResponse; the hall dialogs (ac/Zb) show the full-screen sign dialog when signInStatus==0; view/dialog/a/k.java requires EXACTLY 8 userSignInList cells; e.java: status==1 = claimed; g.java (POST callback) reads data.signInId + renders the day's rewards (>=4 rewards = last-day bookkeeping), then refreshes the wallet. signInStatus 2 = cycle complete -> MainModel/Zb chains INTO the week-sign surface (bc.e -> GET daily/sign/in); error 8006 ("The event has ended") reaches the same chain |
| POST /activity/api/v1/signIn | campaignSignIn | CampaignApi.signIn -> Map<String,Integer>; the server claims the first unclaimed day of the monthly 8-day cycle, awards the day's golds, returns {"signInId": N}; double-claim returns 7012 (CampaignOnError family) |
| GET /activity/api/v1/lucky/turntable/gold/status | turntableStatus | ICampaignApi.getTurntableRedPoint -> TurntableStatus{isFree}; b/a.java: isFree > 0 paints the jackpot red-point icon. Real state: 1 while today's free draw is unused |
| GET /activity/api/v1/slot/machine/user/gold/draw/status | turntableStatus | same TurntableStatus contract (ICampaignApi.getGoldDrawStatus) |
| POST /datareport/api/v1/event/report | eventReport | IReportInfoApi.reportSandboxData(EventRequest{eventRequests[],packageName}); the impl hits getMetaDataBaseUrl() (patched -> loopback) as PRIMARY. Persisted verbatim to localapi/datareport/event-<yyyymmdd>.jsonl |
| POST /datareport/api/v1/funnel/event/report | funnelReport | IReportInfoApi.newReportSandboxData(List<NewEventInfoRequest>); persisted to funnel-<day>.jsonl |
| POST /datareport/api/v1/app/ping/report/batch | pingReport | IPingReportApi.reportPingEvent(PingEventDto, CloudFront-Viewer-Country + deviceId headers); persisted to ping-<day>.jsonl |

appConfig gained the explicit `isShowUniversalActivity: false` +
`universalActivityVersionCode: 0` keys (b/b.java reads them for the
universal-activity gate; missing keys Gson-default silently).

## Routing pipeline note (verified this session)

RetrofitFactory.httpsCreate passes the inline CloudFront literal as the
Retrofit baseUrl and getMetaDataBackupBaseUrl() as the interceptor's
backup. patch_urls.py rewrites App.smali's setBaseUrl/setBackupBaseUrl
const-strings, so at runtime: primary attempt -> CloudFront (fails fast,
no network) -> BaseUrlInterceptor.switchServer retries against
http://127.0.0.1:18080. The datareport APIs differ: they use
getMetaDataBaseUrl() (the patched PRIMARY) and reach the loopback on the
first attempt. Either way every decoded route lands on the embedded server.

## Call-site evidence table for the remaining default endpoints (Session 19)

Decoded from jadx classes1-4 + dex string scans; a method counts as LIVE
only when a non-interface class invokes it. The wrapper definitions inside
the Api impl classes themselves do not count.

| Cluster (routes) | Verdict | Evidence |
|---|---|---|
| IVIPApi (GET /shop/api/v1/shop/users/vip, PUT buy/vip) | dead code | grep across classes1-4: the interface + impl are referenced NOWHERE; the app's VIP flow goes through Google Play billing (VipService ARouter provider, VipManager) |
| worldCup family (10 routes: campaignGameList, bet, history, notice, integral, ranks, task v1, reward v1) | dead code | every method is @Deprecated in ICampaignApi and has ZERO non-interface call sites (the apparent "getTaskList/rewardList callers" were UserApi/GameApi name collisions) |
| GET /config/files/blockymods-activity-logo (CampaignLogo), GET /config/files/campaign-precious-reward (List<Integer>) | dead code | ICampaignApi.campaignLogo/campaignPreciousReward: 0 call sites |
| videostars (5 routes: config/get, billing/list/get, getbycode, cashapply, exchange) | gated off for local accounts | MoreViewModel guards with `login && !TextUtils.isEmpty(starCode)`; locally-created accounts never carry a starCode, so the calls never fire |
| GET /game/api/v1/games/ugc/status | dead code | IGameApi.getUGCGameStatus: 0 call sites |
| POST /user/api/v1/emails/password/reset | dead code | IUserApi.resetPassword has no live caller; the live reset path is resetPasswordBySecretQuestion (implemented) |
| POST /user/api/v1/user/password (phone SMS retrieve) | dead code | retrievePassword(PhoneBindForm): no live caller; account security uses secret questions + set-password (both implemented) |
| GET /config/files/blockymods-banner (List<BannerEntity>), game-detail-to-editor (Map<String,List<String>>), indiegame-moregame_introduction (List<BannerInfo>), bg-tube-activity-config | empty = honest state | live interfaces, but an empty banner/editor list is the real "no active campaign" response; the handlers keep schema-true defaults |
| halloween (6 routes), bgtube (3 routes) | event-gated | the halloween module + bgtube surfaces only fire during an active event config; with the current appConfig (isShowHallowmasChest false etc.) they stay unreachable — documented-deliberate |

# Wave 5w (Session 19 cont.): the turntable draw chain + the jackpot surface lit

| Route | Handler | Client evidence |
|---|---|---|
| GET /game/api/v1/game/{gameId}/turntable | turntableInfo | IGameApi.getAdsTurntableInfo -> List<AdsTurntableInfo{id,picUrl}>; gamedetail Z.b -> W.onSuccess opens AdsTurntableDialog but BAILS on an empty list — the handler serves 8 real prize slots |
| GET /game/api/v1/game/{gameId}/turntable/props | turntableProps | IGameApi.getAdsTurnHaveReward -> String tip rendered into tvTip (Y.onSuccess); real tip reflects the daily free-draw state |
| PUT /game/api/v1/game/{gameId}/turntable | turntableDraw | IGameApi.getAdsTurntableReward -> Long prize id; AdsTurntableDialog.getRewardPosition matches the id to a wheel position. Real state: one free draw per UTC day, prize golds credited, isFree flips to 0 |
| (appConfig) | isShowUniversalActivity=true | b/b.java gates the slot_machine jackpot icon on isShowUniversalActivity && versionCode (App sets activityId="slot_machine"); flipping it lights the hall icon and the draw-status polling |

The lucky/turntable + slot draw status handlers now read REAL state
(turntableFreeToday) instead of a constant — after a successful draw the
red-point icon goes gray until the next UTC day, exactly like a real
backend's daily free-draw rule.

Automation: Phase A handles the (now reachable) campaign sign dialog
defensively — dvSignUp + Claim tap -> bounded POST + reward-popup
dismissal, BACK fallback, all non-fatal. The jackpot draw-status poll is
asserted as a [probe] line first, to be promoted to a hard check once
observed on-device.

# Wave 5w cont.: per-game ads-CD config real + final classification

| Route | Handler | Evidence |
|---|---|---|
| GET /config/files/indiegame-{gameId} + indiegame-new-{gameId} | adsCdConfig | IUserApi.getAdsCdConfig/getNewAdsCdConfig -> AdsCdConfig{adsCdTimeFirst, adsCdTimeSecond}; AppInfoCenter's getter falls back to 0/0 when unloaded — the handler serves real 30/60 s cooldowns |
| PUT /shop/api/v2/pay/game/{gameId} (bugGame) | gated: unreachable | gamedetail Z line 20 fires it only in the PAID-game buy flow (isPay==1); every local catalog game serves isPay=0 (deliberate: the local world sells no games) — the buy-game chain stays documented-gated |

Every one of the remaining 42 default routes now carries an explicit
verdict (dead code / event-gated / account-gated / honest empty) in the
tables above. Host rig 399/399.

# Wave 6c (Session 20): the activity-task chain goes real

The Session-19 verdict "activity/action + receive/reward gated by the
empty activityTitle" is RESOLVED by lighting the title surface — the
client does the rest on its own.

| Route | Handler | Client evidence |
|---|---|---|
| GET /activity/api/v2/activity/title | activityTitle (real) | MainModel bc.b -> Lb.onSuccess: a NON-EMPTY list makes the client register per-title red points (e.b.c.f.b) and IMMEDIATELY fetch the actions for "weekend"/"weekday" (DateUtils.isWeekend(serverTime) picks which). Titles carry countryList=[] (passes f.a's language filter), endTime=-1 (no expiry), isEnable=true |
| GET /activity/api/v1/activity/action?titleType= | activityActionList | ICampaignApi.getActivityTaskActionList @GET; MainModel bc.a -> Mb feeds "online_time" quantities (10/30/60 min buckets known to the client's analytics) into the local countdown (ActivityTaskCountDownUtils). Status semantics decoded: 0 in-progress, 1 claimable (o's constructor lights the per-action red point), 2 claimed |
| POST /activity/api/v1/receive/reward?titleType=&actionId= | activityTaskReward | ActivityTaskContentItemViewModel o.h -> CampaignApi.getActivityTaskReward; n.onSuccess sets status 2 + shows CampaignGetIntegralRewardDialog with the actionRewards. Server: 7012 double-claim, generic fail while incomplete, wallet credit on success |

State model (nothing hardcoded): per-user per-day `activity` bucket in
state.json — onlineMinutes tracked by the server (one credit per DISTINCT
UTC minute with authenticated traffic, ticked from requireUser),
lastDayLogin stamped on the first request of the day, claimed map keyed
"a<actionId>". Actions mirror the client's own flag vocabulary:
weekday = online_time 10/30/60 min (200/400/800 golds), weekend =
online_time 10 min (300 golds) + saturday_login + sunday_login (200
golds, complete only on their real UTC weekday with a login that day).
cumulativeTime on the title response = the tracked minutes (the client
adds them to its local countdown).

Coverage now: 335 discovered / 295 implemented / 40 default — every
remaining default still carries its verdict in the tables above.
Host rig 399 -> 420 checks (21 new: title shape + filter semantics,
action shape per type, fresh-user in-progress state, incomplete/unknown
claim rejection, injected-minutes completion via the state file, claim +
wallet credit + 7012, day-aware login-task claims, cumulativeTime
read-back). The on-device run observes the client fetching
/activity/api/v2/activity/title and (for the first time)
/activity/api/v1/activity/action?titleType=... on its own at boot.

# Wave 7 (Session 21): the integral/task family classified + the claim surface driven

## Verdict table for the last unclassified activity routes (jadx classes1-5)

Every ICampaignApi method below is @Deprecated AND its CampaignApi static
wrapper has ZERO non-wrapper call sites (grepped all five dex source
trees; the only hits are entity field getters or OTHER APIs' methods with
the same name — halloween's IHalloweenApi.getTaskList(language, "thanks_giving"),
TribeApi.getTaskReward = the implemented /tribe task route, and
CampaignRedPoint.getIntegralReward()/CampaignRankRewardWithTime.rewardList
getters). Same dead-code class as the worldCup family.

| Route | Verdict | Evidence |
|---|---|---|
| GET /activity/api/v1/activity/task (getTaskList, List&lt;CampaignTask&gt;) | dead code | @Deprecated; CampaignApi.getTaskList wrapper: 0 external callers |
| PUT /activity/api/v1/activity/task/reward (getTaskReward, Integer) | dead code | @Deprecated; wrapper 0 external callers (TribeApi.getTaskReward is the DIFFERENT implemented tribe route) |
| GET /activity/api/v1/activity/integral/rank (totalRank, PageData&lt;CampaignRank&gt;) | dead code | @Deprecated; wrapper 0 external callers |
| GET /activity/api/v1/activity/user/integral/rank (myRank, CampaignRank) | dead code | @Deprecated; wrapper 0 external callers; no reference to myRank anywhere outside the interface+wrapper |
| GET /activity/api/v1/activity/user/integral/reward (rewardList, CampaignReward) | dead code | @Deprecated; wrapper 0 external callers (hits are CampaignRankRewardWithTime.rewardList field getter + FirstTopUp/ExchangeResponse fields) |
| PUT /activity/api/v1/activity/user/integral/reward (getIntegralReward) | dead code | @Deprecated; wrapper 0 external callers (CampaignRedPoint.getIntegralReward is an entity getter) |
| GET /activity/api/v1/activity/user/rank/reward (getRankReward, CampaignRankRewardWithTime) | dead code | @Deprecated; wrapper 0 external callers |

All 335 discovered routes now carry an explicit verdict; 40 remain
default (dead code / event- or account-gated / honest empty), 295 are
state-backed handlers.

## The activity-task claim surface, walked end-to-end through the real UI

Full jadx decode of the path the UI drive now takes (session 21):

1. Hall top bar (content_header1): item0=icon_discover, item1=icon_activity
   (+red point binding_3), item2=icon_vip, item3=icon_scrap. The binding
   (ka.java) wires item1 -> MainFragmentViewModel.onActivity.
2. onEnterActivity -> bc.j -> D.b -> TemplateUtils.startTemplate(
   ActivityFragment (e.b.c.b), title string game_g1008). The template's
   title bar literally reads "Bed Wars" (client string-reuse quirk).
3. ActivityFragment -> ActivityViewModel (e.b.c.g) -> ActivityListModel
   (e.b.c.f) -> CampaignApi.getActivityTaskTitleList -> the wave-6c title
   handler. Cards render from item_activity_list (bg_content card,
   iv_pic image, timer, per-title red point).
4. Card click (ActivityItemViewModel e.b.c.c.f): titleType "weekend" or
   "recharge" -> ActivityNewDialog (m, FullScreenDialog, layout
   activity_content_temp_weekend). "weekday" falls into the content
   switch (inside-url / url / activity:wheel|slot_machine|sign|...) —
   with the local content ("Play to earn rewards") it is inert.
5. ActivityNewDialog -> ActivityTaskContentListModel (q):
   q.onLoad fetches GET /activity/api/v1/activity/action?titleType=
   FRESH on every dialog open (a second client-asserted action surface
   beyond the boot-time fetch). online_time rows compute their local
   progress from the client countdown + server cumulativeTime; status
   0/1/2 semantics as decoded in wave 6c.
6. Row button (item_activity_task_content, text = string/receive "Get",
   NO resource-id, binding_6) -> ActivityTaskContentItemViewModel o.h ->
   POST /activity/api/v1/receive/reward?titleType=&actionId=.
   n.onSuccess: status=2, per-title red point removed, and
   CampaignGetIntegralRewardDialog (Confirm = base_sure) with the
   actionRewards.

Automation (scripts/ui_automation_test.py):
- Phase H: hall rb_1 -> swipe-down to expand the collapsing header ->
  tap item1 -> tap the weekend card (index 1 of bg_content; falls back
  to index 0 once) -> poll the "GET" buttons -> tap the first (= the
  10-min online_time row) -> hard check POST receive/reward 0->1 ->
  dismiss the Confirm dialog; wallet read-back via GET /pay/api/v1/
  wealth/user before/after.
- Invite hardening (standing session-20 item): a SECOND friend candidate
  (fqb*) joins via the API so the invite screen is denser and the row
  find has a fallback nick; one bounded invite-screen RE-ENTRY tap of
  ibTemplateRight mid-wait (runs 37421024074/37423815542 missed the
  first transition).

## Run 37436975853 (PASS): both chains client-asserted in a single run

- G: inviteFriend client-asserted (POST 0->1, invitee sees the type-2
  message=True) — the G-sheet race is fixed by the screen-normalization
  walk; hand-over chief green a 5th time.
- H: the FULL claim chain — item1 found at (276,208), weekend dialog
  opened (3 GET buttons), POST /activity/api/v1/receive/reward 0->1,
  wallet 42000 -> 42300 golds (exactly the weekend 10-min online_time
  reward). The server's own read-back before the drive:
  "weekend online_time status=1" (the wave-6c tracking made the task
  claimable during the run). 40 unique endpoints, no FATAL, PASS.
- COVERAGE.json regenerated: 335 / 295 implemented / 40 default /
  234 host-tested / 136 client-asserted (receive/reward + activity/
  action + member/invite now carry the client_asserted flag).

# Wave 8 (Session 23): vipDress classified dead + sign-in semantics corrected

| Route | Verdict | Evidence |
|---|---|---|
| GET /decoration/api/v1/vip/decorations/users/{typeId} (vipDress) | dead code | @Deprecated; ZERO call sites across classes1-5 (only the IDecorationApi declaration — not even a static wrapper exists) |

Sign-in status semantics corrected to the client contract (Handlers.java +
host tests, 422/0):
- GET /user/api/v2/users/{userId}/daily/sign/in — DailySignInfo.status is
  the CLIENT's enum (WeekSignDialog item j/h.java): 0 = "It isn't time to
  sign in", 1 = claimable (the click fires the claim chain k.a -> PUT
  clickSignIn), 2 = "Received". The previous mapping (claimed = 1) kept
  the WeekSignDialog unreachable forever (MainModel/Xb opens the dialog
  only when some day is 1) and mis-labelled claimed days as claimable.
- GET /activity/api/v1/signIn — MainModel/Zb.java chains INTO the
  week-sign surface (bc.e -> GET daily/sign/in -> WeekSignDialog) ONLY on
  signInStatus == 2 (cycle complete) or error 8006 ("The event has
  ended"). The server now emits 2 when the 8-day cycle is fully claimed;
  mid-cycle stays 0 (claimable today) / 1 (claimed today). Full chain:
  MainActivity -> nb (ya.b isSignIn read) -> CampaignManager
  .getActivitySignUp -> bc.a(ctx,true) -> ya.a isPlayed read -> _b fires
  CampaignApi.signInList when the user has NOT played yet -> Zb.

# Wave 9 (Session 24): rank podium client contract + getScrapNum IM-gated verdict

Server semantics fix (Handlers.java regionRankHome, host tests 422/0):
- GET /ranking/api/v1/ranking/region/home/page/info — the podium is ONE row
  per category, not the top-3 of a single board. Client decode: the item VM
  (overviewrank/f.java) maps TopRankInfo.type to the matching rank template —
  "gDiamond" -> W.c.h, "active" -> W.a.h, "clan" -> W.b.h — and ANY other
  value falls into b2 == -1 -> return (the podium tap is a SILENT NO-OP).
  The previous "gold"-typed rows made the whole category-rank surface dead
  against the real client even though every route returned HTTP 200.

getScrapNum reachability verdict (session 23 handover item, closed):
- GET /activity/api/v1/collect/exchange/user/scrap/{scrapId} (getScrapNum,
  implemented + host-tested) has EXACTLY ONE call site across classes1-5:
  ScrapAskHelpProvider (k.java) — the RongCloud IMKit message provider that
  renders a FRIEND's ScrapAskHelpMessage in a PRIVATE conversation. The
  scrap BAG item tap does NOT fire it (ScrapBagItemViewModel sends
  TOKEN_SEND_SCRAP_CARD — an IM message, not an HTTP call). The route is
  therefore IM-gated and stays not client-assertable locally while the
  RongCloud transport remains out of scope (non-HTTP proprietary protocol).

Phase L (rank surface drive, scripts/ui_automation_test.py):
- Me tab (rb_5) -> "Ranking" row -> OverViewRankActivity: hard check on
  GET /ranking/api/v1/ranking/region/home/page/info (0->N).
- Tap the FIRST podium row (tv_rank_type_top1_name; server order
  [gDiamond, active, clan] -> the gDiamond template W.c.h): hard checks on
  GET /ranking/api/v1/gold/diamond/region/weekly/rank (0->N) and
  GET /ranking/api/v1/ranking/user/info (0->N); the template's second
  pager page (period, global) prefetches or fires via the real
  rb_global_tab tap -> GET /ranking/api/v1/gold/diamond/global/weekly/rank.

# Wave 10 (Session 25): item2 VIP entry DECODED (not service-gated) + podium rows 2+3 drives

item2 VIP reachability verdict (session 24 handover item, closed):
- The hall header's item2 (content_header1) / littleItem2 (content_header2)
  fires MainFragmentViewModel.onEnterVip -> VipManager.enterVipFragment.
  VipManager.<clinit> resolves IVipService via
  RouteServiceManager.provide("/subs/service") — and that route IS
  registered: smali_classes4/com/sandboxol/vip/service/VipService.smali
  carries @Route(path = "/subs/service") and appears in
  ARouter$$Providers$$vip / ARouter$$Group$$subs. The "service-gated, may
  be a no-op" worry from session 24 is DECODED: the entry works locally.
- VipService.enterVipFragment -> TemplateUtils.startTemplate
  (com.sandboxol.vip.view.fragment.main.n = PrivilegeCenterFragment) whose
  PrivilegeCenterViewModel.initData() calls VipApi.getSubscribeInfo ->
  GET /pay/api/v1/sub/info/get (exactly one call site in the whole vip
  package). The server response (playerInfo{vip,expireDate,...} + subInfo[])
  matches the client entity com.sandboxol.center.entity.VipSubInfo.
- Phase M (scripts/ui_automation_test.py) drives item2/littleItem2 and
  hard-checks GET /pay/api/v1/sub/info/get 0->N, printing the REQ-path
  delta as evidence.

Phase N (rank podium rows 2+3, the natural completion of Phase L):
- Phase L taps only the FIRST podium row (gDiamond -> W.c.h). The podium
  emits one row per category ([gDiamond, active, clan]) and the item VM
  (overviewrank/f.smali) maps "active" -> W.a.h, "clan" -> W.b.h with the
  podium period (rank_period_type) in the template bundle. The template
  list models W.a.n / W.b.n fire the active/clan boards + the shared
  ranking/user/info.
- Phase N re-opens the Ranking screen, sorts all tv_rank_type_top1_name
  rows by (y,x), taps row 1 (active) and row 2 (clan) on the WEEK podium,
  then flips rb_overall_tab (activity_overview_rank.xml) and repeats on the
  OVERALL podium. Hard checks (all 0->N, pre-counted before the walk):
  active/{region,global}/weekly, clan/{region,global}/weekly,
  active/{region,global}/overall, clan/{region,global}/overall — with the
  rb_global_tab fallback for the template's second pager page (Phase L
  pattern). CI timeouts bumped (UI step 32 -> 40 min, workflow 45 -> 55)
  to absorb the added phases.

## Wave 10 amendment (run 37492582973 triage): the clan rank template is GLOBAL-ONLY

Client decode (e/b/W/b/p.smali ClanRankViewModel + fragment_clan_rank.xml):
- ActiveRankViewModel constructs TWO pager pages — area 0 (region) + area 1
  (global); both fetch on open; fragment_active_rank.xml carries
  rb_area_tab + rb_global_tab.
- ClanRankViewModel constructs ONE page only — W/b/o(ctx, period, area=1
  GLOBAL); fragment_clan_rank.xml carries ONLY rb_global_tab.
- Consequence: GET /ranking/api/v1/clan/region/weekly/rank and
  GET /ranking/api/v1/clan/region/overall/rank have NO reachable client
  call path from the podium. They stay implemented + host-tested but are
  NOT client-assertable; Phase N hard-checks the clan GLOBAL boards only
  (clan/global/weekly + clan/global/overall asserted).

Run 37492582973 verdicts (Phase M/N first live drive):
- ACTIVE: region/weekly 0->1 + global/weekly 0->1 (both pager pages) —
  client-asserted on the first attempt.
- CLAN: the template opened and its global page fetched (clan/global/
  weekly 0->1); the region check failed exactly as the decode predicts —
  the check is removed per the contract above.
- Phase L flake (post-K-relaunch): the Me-tab "Ranking" row was tapped on
  a stale list position and OverViewRankActivity never opened; the podium
  fetch 0->0 FAILed and the app stayed on the Me tab, which also starved
  Phase M's header walk (item2 lives on the HALL tab; rb_1 exists on
  every main tab so the old precondition passed on the wrong screen).
  Fixes: L/N walks now VERIFY the open (podium fetch delta / podium rows)
  and retry once; Phase M grounds on the HALL TAB by tapping rb_1 first.
- Overall-leg drift: after the week drives the template self-closed to
  the hall (the documented drift) — the overall leg now re-opens the
  ranking screen when the podium rows vanish before flipping
  rb_overall_tab.
- Registration gate: the final account-creation check failed on
  logcat BUFFER ROTATION (the D-phase set-password fcalls passed live
  but their REQ lines rotated out). Fix: paths_mid snapshot captured
  right after Phase D and unioned into the final path set.

## Wave 10 amendment 2 (run 37499606354 PASS): M/N client-asserted + bonus vip products route

- ALL 6 new ranking routes client-asserted: active/{region,global}/weekly,
  active/{region,global}/overall, clan/global/weekly, clan/global/overall
  (Phase N, all 0->N). Phase L stayed green (podium 0->2, gDiamond both
  boards). COVERAGE.json regenerated: 154 client-asserted.
- Phase M client-asserted GET /pay/api/v1/sub/info/get 0->1 (item2 ->
  privilege center) AND the run's evidence delta revealed the privilege
  center flow ALSO fires GET /pay/api/v2/pay/products/vip
  (BillingManager.vipSubsProductsList <- vip/view/fragment/main/p) —
  decode confirmed, hard check added (expected 155 on the next green).
- deep-drive additions (evidence: run 37492582973's delta fired both):
  GET /video/api/v1/app/video/list/{type} (client resolved {type} to
  "new"/"top" during the game-detail walk) and GET /decoration/api/v1/
  decorations/{otherId}/using (client resolved {otherId} to the live
  user id) — hard checks added with split-literal honesty so only these
  two templates are claimed.

## Wave 11 (session 26): the login-surface contract fixes (IUserLoginApi decode)

The sandbox was reset this session (prior jadx_out/APK artifacts gone; base
APK re-pulled from release v0.6.1-guidefix, jadx 1.5.6 reinstalled, per-dex
decompile redone). classes2 decode (com/sandbox/login/web/IUserLoginApi —
the login-screen API surface) exposed two response-contract defects that
Gson could not parse, plus a systematic audit that found no others:

| Route | Was | Client model (jadx) | Now |
|---|---|---|---|
| GET /user/api/v1/user/set-psd/param/check | data:{} (JsonSyntaxException on HttpResponse\<Long\>) | `HttpResponse<Long>` paramCheck(@Query type) | data: server-millis Long (envelope "num") |
| POST /user/api/v1/account/invalid/check | ackPost → no data field (Boolean stayed null) | `HttpResponse<Boolean>` accountCheck(@Header bmg-device-id, @Header bmg-sign, @Query account, @Query loginTypeId, @Query type) | data: false Boolean, real handler (pre-auth, stateless) |

- Value semantics: paramCheck's Long is used by the set-password flow (the
  SetPasswordForm carries account/password/confirmPassword/userId — no
  param field, so the Long is consumed by the caller); server-millis is the
  type-true stand-in until the call-site decode lands. accountCheck's
  Boolean branch (invalid vs available) is pending the LoginActivity call
  site (classes1); "false = not invalid" is the permissive local reading.
  Both documented as uncertain-value/type-certain — the crash itself was
  the client-visible defect.
- RoutingTable audit (script over all 335 entries): NO phantom H: mappings
  (every H: name dispatches in Handlers.handle). The remaining ackPost/ackPut
  routes were cross-checked against their client models: pay/v1 recharge
  (raw HttpResponse), user/language, user/mac/id, user/device/id (all raw
  HttpResponse) — generic ack is contract-true for all of them.
- Host rig: +4 checks (Long-parse, Boolean-parse, stateless-false,
  probe-visitor) → 426/426.

## Wave 11 amendment 2 (decode complete): paramCheck Long + accountCheck Boolean value semantics

The parallel-session handlers fixed the TYPES (Long/Boolean — the {}
default crashed Gson); the VALUE semantics are now decoded from the call
sites and the handlers refined:

- GET /user/api/v1/user/set-psd/param/check (IUserLoginApi.paramCheck,
  only caller chain LoginService -> web.b.b): the consumer is
  GooglePlayPayService recharge onSuccess (classes3) for a passwordless
  account — onSuccess(Long l) { if (l > 100)
  IntentUtils.startPasswordSettingDialog(context, false); }. The Long is
  a PROMPT THRESHOLD, not a timestamp. Local policy: 200 (prompt) for a
  resolved user without a password, 0 for a secured account.
- POST /user/api/v1/account/invalid/check (IUserLoginApi.accountCheck ->
  the guest SetAccountViewModel, classes2 f/a/a/h): onSuccess(true) ->
  TwoTextButtonDialog "login_set_account_confirm <name>" -> accountModify
  (name FREE); onSuccess(false) -> base_set_account_exits helper
  ("Account already exists") and the flow STOPS. A constant false (the
  first implementation) BLOCKED the whole set-account surface. The local
  server now answers from real state: taken -> false, free -> true.

Host rig: both value branches tested (free name true, taken name false;
register-then-check). The "Account already exists" string and the dialog
flow make the decode unambiguous.

## Wave 11 amendment (run 37546126594 triage): the RSA password contract — real crypto, real server

Discovery (error-driven, from the client's own traffic):
- Run 37546126594 FAILED on the G hand-over check, but the diagnostics
  artifact exposed a REAL API bug that every prior run had missed: Phase O's
  client-UI login submitted POST /user/api/v2/app/login and the server
  answered with a 37-byte ERROR envelope ({"code":0,...}) — the check only
  counted the REQ line, never the response, so the client-UI login had
  silently never worked against the local backend.

Client decode (jadx, classes2.dex):
- com.sandbox.login.web.b ("UserLoginApi" wrapper) encrypts passwords with
  LoginHelper.b -> RSAUtils.f.a BEFORE every request:
  * POST /user/api/v2/app/login            LoginRegisterAccountForm.password
  * POST /user/api/v2/app/set-password     SetPasswordForm.password + confirmPassword
  * POST /user/api/v2/user/password/modify ChangePasswordForm.old/newPassword (+confirm)
  * POST /user/api/v1/user/password/check  @Query("password")
- Cipher: RSA/ECB/PKCS1Padding, 1024-bit hardcoded X509 public key
  (com.sandbox.login.e.e), 117-byte chunks, custom Base64 (NO_WRAP).
- Fallback contract: LoginHelper.b returns the PLAINTEXT when its cipher
  throws — the v1 login wrapper (POST /user/api/v1/login) sends plaintext
  and v1/register has always been plaintext.
- The v2 login also sends @Header bmg-device-id (androidId) + bmg-sign
  (CommonHelper.getSignature) — currently accepted unverified (documented,
  not fake-validated).

Server implementation (the production keypair is unrecoverable — the
private half lived on the real backend and exists nowhere in the client,
the archives, or the Engine 10068 source):
- localapi-server RsaCipher.java: a FIXED 1024-bit keypair minted for the
  local world. decryptIfEncrypted() = Base64 (whitespace-tolerant) -> whole
  128-byte blocks -> RSA/ECB/PKCS1Padding chunked decrypt -> UTF-8; ANY
  mismatch returns the raw value, so plaintext v1 flows and host-rig fcalls
  pass through untouched (mirrors the client's own lenient fallback).
- scripts/patch_rsa_key.py (wired into build_signed_apk.sh): swaps the
  client's hardcoded public-key constant in the apktool smali tree for OUR
  public key — idempotent, fatal if the original key survives. The client
  code path is unchanged; only the key constant differs (same category as
  the URL rewiring).
- Handlers: login / setPassword / passwordModify / passwordCheck now
  decrypt for real. The stored password remains the PLAINTEXT the flow
  set (register/set-password/modify all decrypt before storing).
- LocalHttpd RES log lines now carry the envelope code
  ("RES POST ... 123b code=1") — traffic observability for UI assertions
  (requirement 15).

Host rig: 422 -> 431 tests. Wave 11 block drives all four encrypted flows
with a dependency-free pure-python PKCS1v15 encryptor that parses the
public key straight out of RsaCipher.java (single source of truth):
v2 login RSA ok + wrong-pw rejected, v1 plaintext passthrough, v2
set-password RSA -> RSA login, v2 password modify RSA, password/check
right+wrong, non-RSA Base64 rejected as wrong-password (never a 5xx).

Phase O automation upgrade: the client-UI login is now hard-checked for
server ACCEPTANCE (RES code=1 delta), not just submission.

NOTE: the minted private key protects nothing in a purely local single-user
world; it is committed so builds and host tests stay deterministic. It is
NOT a repository credential. The G hand-over flake (PUT never fired despite
every tap landing) is now a 2-attempt drive with a failure dump — evidence
for the next triage, not yet root-caused.
