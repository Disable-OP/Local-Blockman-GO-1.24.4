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

