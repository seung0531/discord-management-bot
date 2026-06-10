import discord
from discord.ext import commands
from discord import app_commands
import re
import asyncio
import os
import json

# 🔥 토큰 (환경변수 사용 권장)
TOKEN = os.environ.get("DISCORD_TOKEN")
# TOKEN = "직접_입력할경우_여기에_입력"

ROLE_NAME = "멤버"
RM_ROLE_NAME = "신입"
AUTH_CHANNEL_ID = 1476798658254082139
KEYWORD = "닉네임"

intents = discord.Intents.default()
intents.typing = False
intents.presences = False
intents.members = True
intents.message_content = True

# ---------------------------------------------------------
# 🔥 [핵심 1] JSON 데이터베이스 설정
# ---------------------------------------------------------
DATA_FILE = "party_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# 봇 구동 시 데이터를 한 번 불러옵니다.
party_data = load_data()


# ---------------------------------------------------------
# 봇 클래스
# ---------------------------------------------------------
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        # 🔥 [핵심 2] 봇이 켜질 때 '진짜 모집글 뷰'를 영구 뷰로 등록
        self.add_view(ActiveMatchmakingView())
        print("슬래시 명령어 동기화 및 데이터 복구 준비 완료!")

bot = MyBot()


# ---------------------------------------------------------
# 인증 기능
# ---------------------------------------------------------
@bot.event
async def on_message(message):
    if message.author.bot or message.channel.id != AUTH_CHANNEL_ID:
        return

    content = message.content.lower()
    
    if KEYWORD.lower() in content:
        role_to_add = discord.utils.get(message.guild.roles, name=ROLE_NAME)
        role_to_remove = discord.utils.get(message.guild.roles, name=RM_ROLE_NAME)

        if role_to_add:
            try:
                await message.author.add_roles(role_to_add)
            except Exception as e:
                print(f"{message.author}님 역할 부여 실패: {e}")

        if role_to_remove:
            try:
                await message.author.remove_roles(role_to_remove)
            except Exception as e:
                print(f"{message.author}님 역할 제거 실패: {e}")

    await bot.process_commands(message)


# ---------------------------------------------------------
# 팝업창 모음 (초기 설정용 - 영구 뷰 불필요)
# ---------------------------------------------------------
class CustomGameModal(discord.ui.Modal, title="게임 이름 직접 입력"):
    game_input = discord.ui.TextInput(label="게임 이름", placeholder="원하는 게임의 이름을 입력하세요.", max_length=50)

    def __init__(self, setup_view):
        super().__init__()
        self.setup_view = setup_view
        if setup_view.selected_game != "-":
            self.game_input.default = setup_view.selected_game

    async def on_submit(self, interaction: discord.Interaction):
        self.setup_view.selected_game = self.game_input.value
        await self.setup_view.update_embed(interaction)


class TimeSetupModal(discord.ui.Modal, title="모집 시간 설정"):
    time_input = discord.ui.TextInput(label="모집 시간", placeholder="예: 오후 8시, 30분 뒤 등", max_length=50)

    def __init__(self, setup_view):
        super().__init__()
        self.setup_view = setup_view
        if setup_view.selected_time != "(아직 없음)":
            self.time_input.default = setup_view.selected_time

    async def on_submit(self, interaction: discord.Interaction):
        self.setup_view.selected_time = self.time_input.value
        await self.setup_view.update_embed(interaction)


# ---------------------------------------------------------
# 🔥 [핵심 3] 임베드 자동 생성기 (JSON 데이터 기반)
# ---------------------------------------------------------
def build_party_embed(party_info: dict) -> discord.Embed:
    embed = discord.Embed(
        title=f"📢 {party_info['game']} 게임 모집 중!",
        color=discord.Color.blue()
    )
    current_count = len(party_info['participants'])
    embed.add_field(name="게임", value=party_info['game'], inline=True)
    embed.add_field(name="모집 정원", value=f"{current_count} / {party_info['slots']}", inline=True)
    embed.add_field(name="모집 시간", value=party_info['time'], inline=False)
    
    if party_info['participants']:
        mention_list = []
        for p in party_info['participants']:
            if p['id'] == party_info['requester_id']:
                mention_list.append(f"👑 {p['mention']} (방장)")
            else:
                mention_list.append(f"• {p['mention']}")
        embed.add_field(name="참여자 명단", value="\n".join(mention_list), inline=False)
    else:
        embed.add_field(name="참여자 명단", value="참여자가 없습니다.", inline=False)
        
    embed.set_footer(text=f"방장: {party_info['requester_name']}")
    return embed


# ---------------------------------------------------------
# 모집 내용 전체 수정 팝업창 (JSON 연동)
# ---------------------------------------------------------
class EditMatchmakingModal(discord.ui.Modal, title="모집 내용 수정"):
    game_input = discord.ui.TextInput(label="게임 이름", placeholder="원하는 게임을 입력하세요.")
    slots_input = discord.ui.TextInput(label="정원 (숫자 입력)", placeholder="예: 5명 또는 5")
    time_input = discord.ui.TextInput(label="모집 시간", placeholder="예: 오후 8시")

    def __init__(self, party_id, party_info):
        super().__init__()
        self.party_id = party_id
        self.game_input.default = party_info['game']
        self.slots_input.default = party_info['slots']
        self.time_input.default = party_info['time']

    async def on_submit(self, interaction: discord.Interaction):
        party = party_data[self.party_id]
        party['game'] = self.game_input.value
        party['slots'] = self.slots_input.value
        
        match = re.search(r'\d+', str(self.slots_input.value))
        party['max_slots_num'] = int(match.group()) if match else 99
        party['time'] = self.time_input.value
        
        save_data(party_data) # 수정된 데이터 저장
        await interaction.response.edit_message(embed=build_party_embed(party))


# ---------------------------------------------------------
# 추방 대상 선택용 드롭다운 메뉴 (JSON 연동)
# ---------------------------------------------------------
class KickParticipantSelect(discord.ui.Select):
    def __init__(self, party_id, party_info, main_message: discord.Message):
        self.party_id = party_id
        self.main_message = main_message
        
        options = [
            discord.SelectOption(label=p['name'], value=str(p['id']))
            for p in party_info['participants'] if p['id'] != party_info['requester_id']
        ]
        
        super().__init__(placeholder="제외할 유저를 선택하세요.", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        target_id = int(self.values[0])
        party = party_data.get(self.party_id)
        
        if not party: return

        # 유저 찾아서 제거
        user_idx = next((i for i, p in enumerate(party['participants']) if p['id'] == target_id), None)
        if user_idx is not None:
            removed_user = party['participants'].pop(user_idx)
            save_data(party_data)
            
            try:
                # 원본 모집글 실시간 업데이트
                await self.main_message.edit(embed=build_party_embed(party))
            except Exception as e:
                print(f"모집글 업데이트 실패: {e}")
            
            await interaction.response.edit_message(content=f"✅ {removed_user['name']}님을 명단에서 제외했습니다.", view=None)
        else:
            await interaction.response.edit_message(content="❌ 대상을 찾을 수 없거나 이미 퇴장한 유저입니다.", view=None)

class KickView(discord.ui.View):
    def __init__(self, party_id, party_info, main_message: discord.Message):
        super().__init__(timeout=60)
        self.add_item(KickParticipantSelect(party_id, party_info, main_message))


# ---------------------------------------------------------
# 🔥 [핵심 4] 채널에 게시된 진짜 모집글 뷰 (영구 뷰)
# ---------------------------------------------------------
class ActiveMatchmakingView(discord.ui.View):
    def __init__(self):
        # timeout=None 필수, 인자(requester 등)는 모두 제거합니다. (재시작 시 비어있게 됨)
        super().__init__(timeout=None)

    def has_permission(self, interaction: discord.Interaction, party_info) -> bool:
        if interaction.user.id == party_info['requester_id']: return True
        if interaction.user.guild_permissions.administrator: return True
        return False

    # 모든 버튼에 custom_id를 고정으로 부여하여 봇 재시작 후에도 추적 가능하게 합니다.
    @discord.ui.button(label="참여", style=discord.ButtonStyle.success, emoji="✋", custom_id="party_join")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        party_id = str(interaction.message.id)
        if party_id not in party_data:
            await interaction.response.send_message("❌ 이미 만료되거나 삭제된 모집글입니다.", ephemeral=True)
            return

        party = party_data[party_id]

        if any(p['id'] == interaction.user.id for p in party['participants']):
            await interaction.response.send_message("이미 모집에 참여 중입니다!", ephemeral=True)
            return
        
        if len(party['participants']) >= party['max_slots_num']:
            await interaction.response.send_message("이미 정원이 가득 찼습니다! 꽉 참 ❌", ephemeral=True)
            return

        # JSON에 유저 데이터 추가
        party['participants'].append({
            "id": interaction.user.id,
            "mention": interaction.user.mention,
            "name": interaction.user.display_name
        })
        save_data(party_data)
        await interaction.response.edit_message(embed=build_party_embed(party), view=self)

    @discord.ui.button(label="나가기", style=discord.ButtonStyle.danger, emoji="🚪", custom_id="party_leave")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        party_id = str(interaction.message.id)
        if party_id not in party_data: return
        party = party_data[party_id]

        user_idx = next((i for i, p in enumerate(party['participants']) if p['id'] == interaction.user.id), None)
        if user_idx is None:
            await interaction.response.send_message("이 모집에 참여하고 있지 않습니다.", ephemeral=True)
            return
        
        party['participants'].pop(user_idx)

        # 방장이 나갔을 경우 처리
        if interaction.user.id == party['requester_id']:
            if len(party['participants']) > 0:
                # 다음 사람에게 방장 위임
                party['requester_id'] = party['participants'][0]['id']
                party['requester_name'] = party['participants'][0]['name']
                save_data(party_data)
                await interaction.response.edit_message(embed=build_party_embed(party), view=self)
            else:
                # 아무도 없으면 삭제
                del party_data[party_id]
                save_data(party_data)
                await interaction.response.send_message("✅ 참가자가 모두 나가 모집이 자동 마감되었습니다.", ephemeral=True)
                await interaction.message.delete()
        else:
            save_data(party_data)
            await interaction.response.edit_message(embed=build_party_embed(party), view=self)

    @discord.ui.button(label="수정", style=discord.ButtonStyle.secondary, emoji="✏️", custom_id="party_edit")
    async def edit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        party_id = str(interaction.message.id)
        if party_id not in party_data: return
        party = party_data[party_id]

        if not self.has_permission(interaction, party):
            await interaction.response.send_message("❌ 방장 또는 관리자만 수정 기능을 사용할 수 있습니다.", ephemeral=True)
            return

        modal = EditMatchmakingModal(party_id, party)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="추방", style=discord.ButtonStyle.secondary, emoji="💥", custom_id="party_kick")
    async def kick_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        party_id = str(interaction.message.id)
        if party_id not in party_data: return
        party = party_data[party_id]

        if not self.has_permission(interaction, party):
            await interaction.response.send_message("❌ 방장 또는 관리자만 인원을 추방할 수 있습니다.", ephemeral=True)
            return

        if len(party['participants']) <= 1:
            await interaction.response.send_message("❌ 내보낼 수 있는 다른 참여자가 명단에 없습니다.", ephemeral=True)
            return

        view = KickView(party_id, party, interaction.message)
        await interaction.response.send_message("명단에서 제외할 유저를 골라주세요:", view=view, ephemeral=True)

    @discord.ui.button(label="쫑", style=discord.ButtonStyle.primary, emoji="🔒", custom_id="party_close")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        party_id = str(interaction.message.id)
        if party_id not in party_data: return
        party = party_data[party_id]

        if not self.has_permission(interaction, party):
            await interaction.response.send_message("❌ 방장 또는 관리자만 모집을 마감할 수 있습니다.", ephemeral=True)
            return
        
        # 데이터 삭제 및 메시지 삭제
        del party_data[party_id]
        save_data(party_data)
        
        await interaction.response.send_message("✅ 모집이 마감되어 창이 삭제되었습니다.", ephemeral=True)
        await interaction.message.delete()


# ---------------------------------------------------------
# 최초 /모집 명령어 호출 및 설정 창 뷰
# ---------------------------------------------------------
class MatchmakingView(discord.ui.View):
    def __init__(self, requester: discord.User):
        super().__init__(timeout=None)
        self.requester = requester
        self.selected_game = "-"
        self.selected_slots = "-"
        self.selected_time = "(아직 없음)"

    async def update_embed(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📝 게임모집 생성", description="설정 후 게시", color=discord.Color.green()
        )
        embed.add_field(name="게임", value=self.selected_game, inline=True)
        embed.add_field(name="정원", value=self.selected_slots, inline=True)
        embed.add_field(name="모집 시간", value=self.selected_time, inline=False)
        embed.set_footer(text=f"요청자: {self.requester.name}")

        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.select(
        placeholder="게임 선택",
        options=[
            discord.SelectOption(label="롤 증바람", value="롤 증바람"),
            discord.SelectOption(label="롤 협곡", value="롤 협곡"),
            discord.SelectOption(label="발로란트", value="발로란트"),
            discord.SelectOption(label="오버워치", value="오버워치"),
            discord.SelectOption(label="롤토체스", value="롤토체스"),
            discord.SelectOption(label="배틀그라운드", value="배틀그라운드"),
            discord.SelectOption(label="스팀 - 직접 입력", value="스팀"),
            discord.SelectOption(label="기타 - 직접 입력", value="기타")
        ]
    )
    async def select_game(self, interaction: discord.Interaction, select: discord.ui.Select):
        if select.values[0] in ["기타", "스팀"]:
            await interaction.response.send_modal(CustomGameModal(self))
        else:
            self.selected_game = select.values[0]
            await self.update_embed(interaction)

    @discord.ui.select(
        placeholder="정원 선택",
        options=[
            discord.SelectOption(label="2명", value="2명"),
            discord.SelectOption(label="3명", value="3명"),
            discord.SelectOption(label="4명", value="4명"),
            discord.SelectOption(label="5명", value="5명"),
            discord.SelectOption(label="6명", value="6명"),
            discord.SelectOption(label="기타 - 모집게시하고 수정으로 인원 변경해주세요", value="n명")
        ]
    )
    async def select_slots(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_slots = select.values[0]
        await self.update_embed(interaction)

    @discord.ui.button(label="시간 입력", style=discord.ButtonStyle.primary, emoji="⏰")
    async def time_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TimeSetupModal(self))

    @discord.ui.button(label="게시", style=discord.ButtonStyle.success, emoji="📢")
    async def post_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.selected_game == "-" or self.selected_slots == "-":
            await interaction.response.send_message("게임과 정원을 모두 선택해주세요!", ephemeral=True)
            return

        await interaction.response.edit_message(content="✅ 모집글이 채널에 게시되었습니다.", embed=None, view=None)

        # 🔥 [핵심 5] 모집글 생성 시 JSON에 저장할 데이터 구성
        match = re.search(r'\d+', str(self.selected_slots))
        max_slots_num = int(match.group()) if match else 99

        temp_party_info = {
            "requester_id": self.requester.id,
            "requester_name": self.requester.name,
            "game": self.selected_game,
            "slots": self.selected_slots,
            "max_slots_num": max_slots_num,
            "time": self.selected_time,
            "participants": [
                {
                    "id": self.requester.id, 
                    "mention": self.requester.mention, 
                    "name": self.requester.display_name
                }
            ]
        }

        active_view = ActiveMatchmakingView()
        msg = await interaction.channel.send(embed=build_party_embed(temp_party_info), view=active_view)

        # 메시지가 정상 전송되면 메시지 ID를 Key값으로 데이터를 JSON에 저장합니다.
        party_data[str(msg.id)] = temp_party_info
        save_data(party_data)


# ---------------------------------------------------------
# 슬래시 명령어
# ---------------------------------------------------------
@bot.tree.command(name="모집", description="게임 모집 창을 엽니다.")
async def matchmaking(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📝 게임모집 생성", description="설정 후 게시", color=discord.Color.green()
    )
    embed.add_field(name="게임", value="-", inline=True)
    embed.add_field(name="정원", value="-", inline=True)
    embed.add_field(name="모집 시간", value="(아직 없음)", inline=False)
    embed.set_footer(text=f"요청자: {interaction.user.name}")

    view = MatchmakingView(requester=interaction.user)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@bot.event
async def on_ready():
    print(f"{bot.user} 봇 실행됨!")

@bot.event
async def on_disconnect():
    print("⚠️ 디스코드 연결 끊김")

@bot.event
async def on_resumed():
    print("✅ 디스코드 재연결됨")


# ---------------------------------------------------------
# 실행 영역
# ---------------------------------------------------------
async def main():
    while True:
        try:
            if TOKEN is None:
                print("❌ DISCORD_TOKEN 환경변수가 설정되지 않음")
                await asyncio.sleep(10)
                continue
            await bot.start(TOKEN)
        except Exception as e:
            print(f"❌ 봇 오류 발생: {e} / 5초 후 재시작")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())

