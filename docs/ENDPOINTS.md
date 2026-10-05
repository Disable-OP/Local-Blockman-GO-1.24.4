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
| GET /user/api/v2/users/{userId}/daily/sign/in | dailySignIn | Map first..seventh DailySignInfo w/ claim status |
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
| GET /ranking/api/v1/ranking/region/home/page/info?rankType= | regionRankHome | RankHomePageInfoResponse: top-3 podium from real wallets/activity/tribe-currency across users+citizens; remainingTime = ms to next Monday UTC |
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
