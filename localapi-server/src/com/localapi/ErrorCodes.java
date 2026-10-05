package com.localapi;

/**
 * Phase 7: client-verified business error codes.
 *
 * Source of truth: the 1.24.4 client's OnError mappers (TribeOnError,
 * UserOnError, GameOnError, ScrapOnError, FriendOnError, GroupOnError,
 * BindOnError, VideoOnError, CampaignOnError) plus the toast strings decoded
 * from resources.arsc. The client's dispatcher (BaseSubscriber.onNext ->
 * OnResponseAdapter.onResponse) delivers EVERY response with code != 1 to
 * OnResponseListener.onError(code, message); the domain mapper turns these
 * exact codes into the proper client toast. Unknown codes fall back to the
 * generic ServerOnError toast, so emitting the right code is what makes an
 * error path behave like the real backend.
 *
 * Evidence: docs/PATCH_PLAN.md "Phase 7" (decompiled mapper + string table).
 */
final class ErrorCodes {

    private ErrorCodes() {}

    // ---- all domains (UserOnError 7 / TribeOnError 7 -> "Please log in") ----
    /** Not logged in / session required. */
    static final int NOT_LOGIN = 7;

    // ---- user (UserOnError) ----
    /** base_account_exists — "Account nickname is already exists" (register). */
    static final int ACCOUNT_EXISTS = 101;
    /** account_not_exist — "User does not exist" (login by uid). */
    static final int ACCOUNT_NOT_EXIST = 102;
    /** sign_in_has_get — "Claimed" (daily sign-in double claim). */
    static final int SIGN_IN_CLAIMED = 7012;
    /** has_illegal_character — "Exist illegal characters" (sensitive word). */
    static final int ILLEGAL_CHARACTER = 7020;

    // ---- tribe (TribeOnError) ----
    /** tribe_not_enough_diamond — "Insufficient Bcubes". */
    static final int TRIBE_NOT_ENOUGH_DIAMOND = 5006;
    /** gold_not_enough — "Coin not enough". */
    static final int GOLD_NOT_ENOUGH = 5007;
    /** tribe_joined — "Already joined". */
    static final int TRIBE_JOINED = 7001;
    /** tribe_name_exist — "Name already exists". */
    static final int TRIBE_NAME_EXIST = 7002;
    /** tribe_not_chief — "You are not Chief". */
    static final int TRIBE_NOT_CHIEF = 7003;
    /** tribe_not_elder — "You are not Elder". */
    static final int TRIBE_NOT_ELDER = 7004;
    /** tribe_full — "Maximum members reached". */
    static final int TRIBE_FULL = 7005;
    /** tribe_not_joined — "You are not in this clan". */
    static final int TRIBE_NOT_JOINED = 7006;
    /** tribe_low_level — "Need higher level" (clan shop level gate). */
    static final int TRIBE_LOW_LEVEL = 7008;
    /** tribe_exceed_max_diamond_or_gold — "Daily maximum reached" (donation caps). */
    static final int TRIBE_DONATION_CAP = 7011;
    /** tribe_task_get_reward — "Reward has been claimed". */
    static final int TRIBE_REWARD_CLAIMED = 7012;
    /** tribe_no_enough_24_hour — "You can join after 24 hours". */
    static final int TRIBE_JOIN_COOLDOWN = 7014;

    // ---- friend (FriendOnError) ----
    /** is_friend_already — "Friends now". */
    static final int FRIEND_ALREADY = 3001;
    /** exceed_max_friend_number — "Friend list full". */
    static final int FRIEND_LIST_FULL = 3002;
    /** no_friend — "Can not modify alias for stranger". */
    static final int FRIEND_ALIAS_STRANGER = 3003;
    /** not_valid_user — "Not valid users". */
    static final int FRIEND_NOT_VALID_USER = 3004;

    // ---- group chat (GroupOnError) ----
    /** group_no_exist_tip — "Group has not exist". */
    static final int GROUP_NO_EXIST = 8102;
    /** new_group_error_8103 — "No permissions now". */
    static final int GROUP_NO_PERMISSION = 8103;
    /** new_group_error_8014 — "The player is not in the group chat". */
    static final int GROUP_NOT_MEMBER = 8104;
}
