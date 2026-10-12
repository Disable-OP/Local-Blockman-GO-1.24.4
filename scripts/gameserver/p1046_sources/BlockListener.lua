--region *.lua
--Date
--此文件由[BabeLua]插件自动生成
BlockListener = {}

function BlockListener:init()
    CEvents.BlockBreakWithMetaEvent:registerCallBack(self.onPlayerAIBreakBlock)
    CEvents.PlayerPlaceBlockEvent:registerCallBack(self.onBlockPlace)
    CEvents.BlockTNTExplodeEvent:registerCallBack(self.onBlockTNTExplode)
    CEvents.BlockTNTExplodeBreakBlockEvent:registerCallBack(self.onBlockTNTExplodeBreakBlock)
    CEvents.SchemeticPlaceBlockEvent:registerCallBack(self.onSchemeticPlaceBlock)
    CEvents.BlockStationaryNotStationaryEvent:registerCallBack(self.onBlockStationaryNotStationary)
    CEvents.BlockTNTExplodeHurtEntityEvent:registerCallBack(self.onBlockTNTExplodeHurtEntity)
    CEvents.ItemPickaxeCanHarvestEvent:registerCallBack(self.onItemPickaxeCanHarvest)
    CEvents.PlayerPlaceBlockBoxJudgeEvent:registerCallBack(self.onPlayerPlaceBlockBoxJudge)
end

function BlockListener.onPlayerAIBreakBlock(rakssid, blockId, blockMeta, vec3, itemID)
    local breakResult = BlockListener.onBlockBreakWithMeta(rakssid, blockId, blockMeta, vec3, itemID)

    local playerAI = AIManager:getAIByRakssid(rakssid)
    if not playerAI then
        return breakResult
    end

    if not breakResult then
        GamePlayerControl.noBreakMap[VectorUtil.hashVector3(vec3)] = 1
    end

    local task = playerAI.breakBlockTask
    if #task > 0 and task[1].x == math.floor(vec3.x) and task[1].y == math.floor(vec3.y) and task[1].z == math.floor(vec3.z) then
        if #playerAI.breakBlockTask > 0 then
            if #playerAI.needBreakBlockList > 0 and VectorUtil.hashVector3(playerAI.breakBlockTask[1]) == VectorUtil.hashVector3(playerAI.needBreakBlockList[1]) then
                playerAI.breakBlockNum = playerAI.breakBlockNum + 1
                table.remove(playerAI.needBreakBlockList, 1)
            end
        end
        table.remove(task, 1)
    end
    if #task == 0 then
        playerAI:stopMove()
    else
        LuaTimer:schedule(function()
            playerAI:breakBlock(task[1])
        end, 50)
    end
    return breakResult
end

local function onBreakBedBlock(player, blockPos)
    if os.time() - GameMatch.startGameTime <= 10 then
        return false
    end
    local toolId = player:getHeldItemId()
    local item = Item.getItemById(toolId)
    if not item then
        MessagesManage:sendSystemTipsToPlayer(player.rakssid, Messages:msgToolNotBreakBed())
        return false
    end
    local class = item:getClassName()
    if class ~= "ItemPickaxe" and class ~= "ItemAxe" and toolId ~= ItemID.SHEARS then
        ---必须使用工具才能破坏床(包括剪刀)
        MessagesManage:sendSystemTipsToPlayer(player.rakssid, Messages:msgToolNotBreakBed())
        return false
    end
    for _, team in pairs(GameMatch.Teams) do
        if team.id == player:getTeamId() then
            ---不能破坏自己队伍的床
            if VectorUtil.hashVector3(blockPos) == VectorUtil.hashVector3(team.bedPos[1])
                    or VectorUtil.hashVector3(blockPos) == VectorUtil.hashVector3(team.bedPos[2]) then
                MessagesManage:sendSystemTipsToPlayer(player.rakssid, Messages:msgNotBreakBed())
                return false
            end
        end
        for _, bedPos in pairs(team.bedPos) do
            if team.isHaveBed and VectorUtil.hashVector3(blockPos) == VectorUtil.hashVector3(bedPos) then
                team:destroyBed(player)
                player:onDestroyBed(team)
                return true
            end
        end
    end
    return false
end

function BlockListener.onBlockBreakWithMeta(rakssid, blockId, blockMeta, blockPos)
    if GameMatch.allowPvp == false then
        return false
    end
    local player = PlayerManager:getPlayerByRakssid(rakssid)
    if not player then
        return false
    end
    local isInArea = TeamConfig:isInTeamArea(blockPos)
    if isInArea == true and blockId ~= 165 then
        return false
    end
    -- Bed Block
    if blockId == BlockID.BED then
        return onBreakBedBlock(player, blockPos)
    else
        if not EngineWorld:isBlockChange(blockPos) then
            return false
        end
    end
    return BlockConfig:isCanBreakBlock(player, blockId)
end

function BlockListener.onBlockPlace(rakssid, itemId, meta, toPlacePos)
    if not GameMatch:isGameStart() then
        return false
    end
    local player = PlayerManager:getPlayerByRakssid(rakssid)
    if not player then
        return false
    end
    MonsterManager:checkInBlock(player, itemId, toPlacePos)
    local isInArea = TeamConfig:isInTeamArea(toPlacePos)
    if isInArea then
        local item = Item.getItemById(player:getHeldItemId())
        if item and item:getClassName() == "ItemCustom" then
            return false
        end
        MessagesManage:sendSystemTipsToPlayer(player.rakssid, Messages:msgBlockPlaceTip())
        return false
    end
    if PropBlockConfig:isPropBlock(itemId) then
        local yaw = player:getYaw()
        local offsetX, offsetZ, rotationX, rotationZ = PropBlockConfig:getOffset(itemId, yaw)
        local schematic = PropBlockConfig:getSchematicFile(itemId, player:getTeamId())
        if schematic ~= nil then
            toPlacePos.x = toPlacePos.x + offsetX
            toPlacePos.z = toPlacePos.z + offsetZ
            EngineWorld:createSchematic(schematic, toPlacePos, rotationX, rotationZ, false, 0, 0, 0, 1)
            player:removeItem(itemId, 1)
            if itemId == 2418 then
                SettlementManager:addBuildScore(player.userId, Define.BuildType.Wall)
            end
            if itemId == 2417 then
                SettlementManager:addBuildScore(player.userId, Define.BuildType.Tower)
                GamePacketSender:broadcastSound(SoundConfig.buildTower, player:getPosition())
            end
        end
        return false
    end
    if BlockID.SPONGE == itemId then
        local sponge_count = 0.5
        local play_count = 4
        LuaTimer:scheduleTimer(function(vec3)
            local posFloat = VectorUtil.newVector3(vec3.x + 0.5, vec3.y, vec3.z + 0.5)
            EngineWorld:addSimpleEffect("haimian.effect", posFloat, player:getYaw(), 1200, 0, sponge_count)
            sponge_count = sponge_count + 0.2
            play_count = play_count - 1
            if play_count == 2 then
                for x = vec3.x - 5, vec3.x + 5 do
                    for y = vec3.y - 5, vec3.y + 5 do
                        for z = vec3.z - 5, vec3.z + 5 do
                            local posInt = VectorUtil.newVector3i(x, y, z)
                            local bId = EngineWorld:getBlockId(posInt)
                            if bId == BlockID.WATER_MOVING or bId == BlockID.WATER_STILL then
                                EngineWorld:setBlock(posInt, 0, 0, 3, true)
                            end
                        end
                    end
                end
            elseif play_count == 0 then
                EngineWorld:setBlock(vec3, 0, 0, 3, true)
            end
        end, 1000, play_count, toPlacePos)
    end
    SettlementManager:addBuildScore(player.userId, Define.BuildType.Place)
    if not AIManager:isAI(rakssid) then
        player.placeBlockNum = player.placeBlockNum + 1
    end
    return true
end

function BlockListener.onSchemeticPlaceBlock(rakssid, vec3, blockId, meta, placeBlockParam)
    if placeBlockParam == 1 then
        local isInArea = TeamConfig:isInTeamArea(vec3)
        if isInArea == true then
            table.insert(GameMatch.cannotPlaceBlock, vec3)
        end
    end
    return true
end

function BlockListener.onBlockTNTExplode(entityId, pos, attr, sourceItemId)

    local player = PlayerManager:getPlayerByEntityId(entityId)
    if player == nil then
        return
    end

    if sourceItemId == ItemID.EXPLOSION_ARROW then
        attr.needSync = false
        attr.isBreakBlock = false
        attr.isHurtEntityItem = false
        attr.custom_explosionSize = GameConfig.explosionSize
        attr.custom_explosionDamageFactor = GameConfig.explosionDamageFactor
    elseif sourceItemId == ItemID.HAND_GRENADE then
        attr.needSync = false
        attr.isBreakBlock = false
        attr.isHurtEntityItem = false
        attr.custom_explosionSize = GameConfig.grenadeExplosionSize
        attr.custom_explosionDamageFactor = GameConfig.grenadeExplosionDamageFactor
        attr.custom_explosionRepelDistanceFactor = GameConfig.grenadeExplosionRepelDistanceFactor
    else
        attr.isBreakBlock = true
        attr.isCanHurt = true
        attr.isHurtEntityItem = false
    end

    if sourceItemId == ItemID.FLARE_BOMB then
        local skill = SkillConfig:getSkill(sourceItemId)
        if skill ~= nil then
            attr.custom_explosionSize = skill.length
        end
    end

    if sourceItemId == BlockID.TNT and player.onWithered then
        attr.custom_explosionSize = GameConfig.tntExplosionSize
        attr.custom_explosionDamageFactor = GameConfig.tntExplosionDamageFactor
        attr.custom_explosionRepelDistanceFactor = GameConfig.tntExplosionRepelDistanceFactor
    end
    local skill_config = SkillConfig:getSkill(sourceItemId)
    if skill_config then
        local tntExplosionSize = skill_config.param[1]
        local tntExplosionRepelDistanceFactor = skill_config.param[2]
        if tntExplosionSize then
            attr.custom_explosionSize = tntExplosionSize
        end
        if tntExplosionRepelDistanceFactor then
            attr.custom_explosionRepelDistanceFactor = tntExplosionRepelDistanceFactor
        end
    end

    return false
end

function BlockListener.onBlockTNTExplodeBreakBlock(blockPos, blockId, sourceItemId)
    local isInArea = TeamConfig:isInTeamArea(blockPos)
    if isInArea then
        return false
    end
    blockId = ItemMapping:getOldItemId(blockId)
    if blockId == BlockID.WHITE_STONE then
        if sourceItemId == ItemID.FLARE_BOMB then
            return false
        end
        if sourceItemId == BlockID.TNT then
            return EngineWorld:isBlockChange(blockPos)
        end
    end
    if blockId == BlockID.OBSIDIAN
            or blockId == BlockID.STAIND_GLASS_PANE
            or blockId == BlockID.STAIND_GLASS then
        return false
    end
    return EngineWorld:isBlockChange(blockPos)
end

function BlockListener.onBlockStationaryNotStationary(blockId)
    return false
end

function BlockListener.onBlockTNTExplodeHurtEntity(sourceItemId, hurtEntityId, placeEntityId)
    local hurter = PlayerManager:getPlayerByEntityId(hurtEntityId)
    if hurter == nil then
        return false
    end
    local placer = PlayerManager:getPlayerByEntityId(placeEntityId)
    if placer == nil then
        return false
    end
    if hurtEntityId ~= placeEntityId
            and placer.team
            and placer.team.id
            and hurter.team
            and hurter.team.id
            and placer.team.id == hurter.team.id then
        return false
    end
    return true
end

function BlockListener.onItemPickaxeCanHarvest(blockId, toolLevel)
    if blockId == BlockID.OBSIDIAN and toolLevel == 4 then
        return false
    end
    return true
end

function BlockListener.onPlayerPlaceBlockBoxJudge(rakssid, blockId)
    local player = PlayerManager:getPlayerByRakssid(rakssid)
    if player == nil then
        return true
    end
    return false
end

return BlockListener
--endregion
