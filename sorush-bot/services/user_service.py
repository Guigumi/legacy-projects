"""
User Service
Business logic for user-related operations
Uses repositories for data access
"""
import logging
import re
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from services.repositories import user_repo, guild_repo, transaction_repo, voice_repo

logger = logging.getLogger(__name__)


class UserService:
    """Service layer for user operations"""
    
    @staticmethod
    def get_user_profile(guild_id: int, user_id: int) -> Dict[str, Any]:
        """Get complete user profile"""
        user = user_repo.get_or_create_user(guild_id, user_id)
        rank = user_repo.get_user_rank(guild_id, user_id, stat='xp')
        
        return {
            'user_id': user_id,
            'username': user.get('user_name'),
            'level': user.get('level', 0),
            'xp': user.get('xp', 0),
            'rank': rank,
            'messages': user.get('messages', 0),
            'voice_mins': user.get('voice_mins', 0),
            'mora': user.get('mora', 0),
        }
    
    @staticmethod
    def process_message(guild_id: int, user_id: int, message_length: int,
                       user_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Process a message for XP and statistics
        
        Returns: {level_up, new_level, xp_gained, total_xp}
        """
        # Create user if doesn't exist
        user_repo.get_or_create_user(guild_id, user_id, user_name=user_name)
        
        # Increment message stats
        user_repo.increment_stat(guild_id, user_id, 'messages')
        user_repo.increment_stat(guild_id, user_id, 'chars_total', message_length)
        
        # Calculate XP
        xp_gained = max(1, message_length // 20)  # 1 XP per 20 characters
        multiplier = guild_repo.get_xp_multiplier(guild_id)
        total_xp = int(xp_gained * multiplier)
        
        # Add XP and check for level up
        xp_result = user_repo.add_xp(guild_id, user_id, total_xp)
        
        return {
            'level_up': xp_result['level_up'],
            'new_level': xp_result['new_level'],
            'xp_gained': total_xp,
            'total_xp': xp_result['new_xp'],
        }

    @staticmethod
    def record_message_activity(
        guild_id: int,
        user_id: int,
        content: str,
        attachments_count: int = 0,
        has_reply: bool = False,
        mentions_count: int = 0,
        user_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record message metrics and timestamps"""
        try:
            user_repo.get_or_create_user(guild_id, user_id, user_name=user_name)
            text = content or ""
            chars = len(text)
            words = len(text.split()) if text.strip() else 0
            n_words = len(text.split()) if text.strip() else 0

            custom_emojis = len(re.findall(r"<a?:\w+:\d+>", text))
            emoji_re = re.compile(
                "[\U0001F300-\U0001F6FF\U0001F1E0-\U0001F1FF\U0001F600-\U0001F64F\U0001F680-\U0001F6FF]",
                flags=re.UNICODE,
            )
            unicode_emojis = len(emoji_re.findall(text))
            emojis_total = custom_emojis + unicode_emojis
            links = len(re.findall(r"https?://\S+|discord\.gg/\S+|discordapp\.com/invite/\S+", text))
            replies = 1 if has_reply else 0

            result = user_repo.increment_user(
                guild_id,
                user_id,
                messages=1,
                chars_total=chars,
                words_total=words,
                emojis_used=emojis_total,
                attachments_sent=attachments_count,
                links_shared=links,
                replies_sent=replies,
                mentions_made=mentions_count,
                n_words_count=n_words,
            )

            if chars > 0:
                user_repo.update_user_max(guild_id, user_id, max_chars_msg=chars)

            user_row = user_repo.get_or_create_user(guild_id, user_id)
            if not user_row.get("first_message_at"):
                user_repo.update_user(guild_id, user_id, first_message_at=datetime.now().isoformat())
            user_repo.update_user(guild_id, user_id, last_message_at=datetime.now().isoformat())

            user_repo.record_daily_activity(guild_id, user_id, messages=1, chars_total=chars)

            return {
                "success": bool(result),
                "chars": chars,
                "words": words,
                "n_words": n_words,
                "emojis": emojis_total,
                "attachments": attachments_count,
                "links": links,
                "replies": replies,
                "mentions": mentions_count,
            }
        except Exception as e:
            logger.error(f"Failed to record message activity for user {user_id}: {e}", exc_info=True)
            return {"success": False}

    @staticmethod
    def add_xp(guild_id: int, user_id: int, amount: int, source: str = "message") -> Dict[str, Any]:
        """Add XP to a user and record source totals"""
        if amount <= 0:
            return {"success": False, "old_xp": 0, "new_xp": 0}

        try:
            user_data = user_repo.get_or_create_user(guild_id, user_id)
            old_xp = user_data.get("xp", 0)
            new_xp = old_xp + amount

            updates = {"xp": new_xp}
            if source == "message":
                updates["xp_from_messages"] = user_data.get("xp_from_messages", 0) + amount
            elif source == "voice":
                updates["xp_from_voice"] = user_data.get("xp_from_voice", 0) + amount
            elif source == "reaction":
                updates["xp_from_reactions"] = user_data.get("xp_from_reactions", 0) + amount

            result = user_repo.update_user(guild_id, user_id, **updates)
            return {
                "success": bool(result),
                "old_xp": old_xp,
                "new_xp": new_xp,
            }
        except Exception as e:
            logger.error(f"Failed to add XP for user {user_id}: {e}", exc_info=True)
            return {"success": False, "old_xp": 0, "new_xp": 0}

    @staticmethod
    def add_xp_with_level_up(guild_id: int, user_id: int, xp_amount: int,
                            source: str = "other") -> Dict[str, Any]:
        """
        Add XP and return level up info
        For use by listeners/events that already have messages/voice tracked separately
        
        Returns: {success, level_up, old_level, new_level, xp_gained}
        """
        try:
            result = user_repo.add_xp(guild_id, user_id, xp_amount)
            if not result or not result.get('success'):
                return {'success': False}
            
            old_xp = result.get('old_xp', 0)
            new_xp = result.get('new_xp', 0)
            
            # Calculate levels
            from services.xp.utils import calculate_level
            old_level, _, _ = calculate_level(old_xp)
            new_level, _, _ = calculate_level(new_xp)
            
            level_up = new_level > old_level
            
            logger.info(
                f"Added {xp_amount} XP ({source}) to user {user_id} in guild {guild_id}: "
                f"Level {old_level} → {new_level}"
            )
            
            return {
                'success': True,
                'level_up': level_up,
                'old_level': old_level,
                'new_level': new_level,
                'xp_gained': xp_amount,
                'old_xp': old_xp,
                'new_xp': new_xp,
            }
        except Exception as e:
            logger.error(f"Failed to add XP for user {user_id}: {e}")
            return {'success': False}

    @staticmethod
    def record_reaction(guild_id: int, reactor_id: int, author_id: int) -> Dict[str, Any]:
        """Record reaction given and received"""
        try:
            user_repo.get_or_create_user(guild_id, reactor_id)
            user_repo.get_or_create_user(guild_id, author_id)

            result_given = user_repo.increment_user(guild_id, reactor_id, reactions_given=1)
            result_received = user_repo.increment_user(guild_id, author_id, reactions_received=1)

            return {
                "success": bool(result_given) and bool(result_received),
                "given": bool(result_given),
                "received": bool(result_received),
            }
        except Exception as e:
            logger.error(f"Failed to record reaction in guild {guild_id}: {e}", exc_info=True)
            return {"success": False}

    @staticmethod
    def start_voice_session(guild_id: int, user_id: int, channel_id: int) -> Optional[int]:
        """Start a voice session"""
        try:
            return voice_repo.start_voice_session(guild_id, user_id, channel_id)
        except Exception as e:
            logger.error(f"Failed to start voice session for user {user_id}: {e}", exc_info=True)
            return None

    @staticmethod
    def end_voice_session(guild_id: int, user_id: int) -> Optional[int]:
        """End a voice session and return duration in minutes"""
        try:
            return voice_repo.end_voice_session(guild_id, user_id)
        except Exception as e:
            logger.error(f"Failed to end voice session for user {user_id}: {e}", exc_info=True)
            return None

    @staticmethod
    def record_voice_minutes(guild_id: int, user_id: int, minutes: int) -> bool:
        """Record aggregated voice minutes"""
        try:
            result = user_repo.increment_user(guild_id, user_id, voice_mins=minutes)
            return bool(result)
        except Exception as e:
            logger.error(f"Failed to record voice minutes for user {user_id}: {e}", exc_info=True)
            return False

    @staticmethod
    def recover_active_voice_sessions() -> int:
        """Recover dangling voice sessions"""
        try:
            return voice_repo.recover_active_sessions()
        except Exception as e:
            logger.error(f"Failed to recover active voice sessions: {e}", exc_info=True)
            return 0
    
    @staticmethod
    def process_voice_activity(guild_id: int, user_id: int, 
                              duration_mins: int, was_streaming: bool = False,
                              was_muted: bool = False,
                              was_deafened: bool = False,
                              user_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Process voice activity for XP and statistics
        
        Returns: {level_up, new_level, xp_gained}
        """
        user_repo.get_or_create_user(guild_id, user_id, user_name=user_name)
        
        # Increment voice stats
        user_repo.increment_stat(guild_id, user_id, 'voice_mins', duration_mins)
        user_repo.increment_stat(guild_id, user_id, 'voice_sessions')
        
        if was_streaming:
            user_repo.increment_stat(guild_id, user_id, 'stream_mins', duration_mins)
        
        if was_muted:
            user_repo.increment_stat(guild_id, user_id, 'muted_mins', duration_mins)
        
        if was_deafened:
            user_repo.increment_stat(guild_id, user_id, 'deafened_mins', duration_mins)
        
        # Calculate XP (less than messages, more for streaming)
        base_xp = max(1, duration_mins // 5)  # 5 mins per 1 XP
        stream_bonus = 1.5 if was_streaming else 1.0
        xp_gained = int(base_xp * stream_bonus)
        
        multiplier = guild_repo.get_xp_multiplier(guild_id)
        total_xp = int(xp_gained * multiplier)
        
        xp_result = user_repo.add_xp(guild_id, user_id, total_xp)
        
        return {
            'level_up': xp_result['level_up'],
            'new_level': xp_result['new_level'],
            'xp_gained': total_xp,
        }
    
    @staticmethod
    def get_leaderboard(guild_id: int, stat: str = 'xp', 
                       page: int = 1, page_size: int = 10) -> Dict[str, Any]:
        """
        Get leaderboard with pagination
        
        Args:
            guild_id: Guild ID
            stat: Statistic to rank by ('xp', 'messages', 'voice_mins', 'mora')
            page: Page number (1-indexed)
            page_size: Number of entries per page
        
        Returns: {data, page, total_pages, has_next, has_prev}
        """
        offset = (page - 1) * page_size
        leaderboard = user_repo.get_leaderboard(
            guild_id,
            stat=stat,
            limit=page_size,
            offset=offset
        )
        
        total_users = user_repo.count(guild_id=guild_id)
        total_pages = (total_users + page_size - 1) // page_size
        
        return {
            'data': leaderboard,
            'page': page,
            'total_pages': max(1, total_pages),
            'page_size': page_size,
            'has_next': page < total_pages,
            'has_prev': page > 1,
            'total_users': total_users,
        }
    
    @staticmethod
    def award_mora(guild_id: int, user_id: int, amount: int,
                  reason: str = "reward") -> Dict[str, Any]:
        """
        Award mora (currency) to user
        
        Returns: {old_mora, new_mora, transaction}
        """
        user = user_repo.get_or_create_user(guild_id, user_id)
        old_mora = user.get('mora', 0)
        new_mora = old_mora + amount
        
        # Update user
        user_repo.update_user(guild_id, user_id, mora=new_mora)
        
        # Record transaction
        trans = transaction_repo.create_transaction(
            guild_id=guild_id,
            user_id=user_id,
            trans_type='earn',
            amount=amount,
            balance_after=new_mora,
            description=reason
        )
        
        logger.info(f"Awarded {amount} mora to {user_id} in {guild_id}: {reason}")
        
        return {
            'old_mora': old_mora,
            'new_mora': new_mora,
            'awarded': amount,
            'transaction': trans,
        }
    
    @staticmethod
    def spend_mora(guild_id: int, user_id: int, amount: int,
                  reason: str = "purchase") -> Dict[str, Any]:
        """
        Spend mora from user's balance
        
        Returns: {success, old_mora, new_mora, insufficient_funds}
        """
        user = user_repo.get_or_create_user(guild_id, user_id)
        current_mora = user.get('mora', 0)
        
        if current_mora < amount:
            return {
                'success': False,
                'insufficient_funds': True,
                'current': current_mora,
                'needed': amount,
                'short': amount - current_mora,
            }
        
        new_mora = current_mora - amount
        user_repo.update_user(guild_id, user_id, mora=new_mora)
        
        # Record transaction
        trans = transaction_repo.create_transaction(
            guild_id=guild_id,
            user_id=user_id,
            trans_type='spend',
            amount=-amount,
            balance_after=new_mora,
            description=reason
        )
        
        logger.info(f"User {user_id} spent {amount} mora in {guild_id}: {reason}")
        
        return {
            'success': True,
            'insufficient_funds': False,
            'old_mora': current_mora,
            'new_mora': new_mora,
            'spent': amount,
            'transaction': trans,
        }
    
    @staticmethod
    def transfer_mora(guild_id: int, from_user_id: int, to_user_id: int,
                     amount: int) -> Dict[str, Any]:
        """
        Transfer mora between users
        """
        # Check sender has enough
        from_user = user_repo.get_or_create_user(guild_id, from_user_id)
        sender_mora = from_user.get('mora', 0)
        
        if sender_mora < amount:
            return {
                'success': False,
                'error': 'insufficient_funds',
                'sender_has': sender_mora,
                'transfer_amount': amount,
            }
        
        # Deduct from sender
        sender_new = sender_mora - amount
        user_repo.update_user(guild_id, from_user_id, mora=sender_new)
        
        # Add to receiver
        to_user = user_repo.get_or_create_user(guild_id, to_user_id)
        receiver_mora = to_user.get('mora', 0)
        receiver_new = receiver_mora + amount
        user_repo.update_user(guild_id, to_user_id, mora=receiver_new)
        
        # Record transactions
        transaction_repo.create_transaction(
            guild_id=guild_id,
            user_id=from_user_id,
            trans_type='transfer',
            amount=-amount,
            balance_after=sender_new,
            description=f"Transfer to {to_user_id}",
            related_user_id=to_user_id
        )
        
        transaction_repo.create_transaction(
            guild_id=guild_id,
            user_id=to_user_id,
            trans_type='transfer',
            amount=amount,
            balance_after=receiver_new,
            description=f"Transfer from {from_user_id}",
            related_user_id=from_user_id
        )
        
        logger.info(f"Transferred {amount} mora from {from_user_id} to {to_user_id}")
        
        return {
            'success': True,
            'from_user': from_user_id,
            'to_user': to_user_id,
            'amount': amount,
            'sender_balance': sender_new,
            'receiver_balance': receiver_new,
        }


# Singleton instance
user_service = UserService()
