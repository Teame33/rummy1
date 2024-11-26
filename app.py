from flask import Flask, render_template, jsonify, request, redirect
import random
import string
import uuid
import time
import threading
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)

# Store active games (in a real application, this should be in a database)
active_games = {}

class Card:
    def __init__(self, value, suit):
        self.id = str(uuid.uuid4())
        self.value = value
        self.suit = suit

    def to_dict(self):
        return {
            'id': self.id,
            'value': self.value,
            'suit': self.suit
        }

class Game:
    def __init__(self):
        self.deck = self.create_deck()
        self.discard_pile = []
        self.creator_hand = []
        self.joiner_hand = []
        self.current_turn = 'creator'
        self.creation_time = time.time()
        self.both_players_joined = False
        self.declared_combinations = {'creator': [], 'joiner': []}
        self.game_winner = None
        self.points = {'creator': 0, 'joiner': 0}
        self.creator_first_discard = False

    def create_deck(self):
        suits = ['♠', '♣', '♥', '♦']  # Spades, Clubs, Hearts, Diamonds
        values = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
        deck = [Card(value, suit) for suit in suits for value in values]
        random.shuffle(deck)
        return deck

    def get_card_value(self, value):
        value_map = {'A': 1, 'J': 11, 'Q': 12, 'K': 13}
        return int(value_map.get(value, value))

    def is_sequence(self, cards):
        if len(cards) < 3:
            return False
        
        # Check if all cards are of the same suit
        if not all(card.suit == cards[0].suit for card in cards):
            return False

        # Sort cards by value
        sorted_cards = sorted(cards, key=lambda card: self.get_card_value(card.value))
        
        # Check if values are consecutive
        for i in range(len(sorted_cards) - 1):
            curr_val = self.get_card_value(sorted_cards[i].value)
            next_val = self.get_card_value(sorted_cards[i + 1].value)
            if next_val - curr_val != 1:
                return False
        
        return True

    def is_set(self, cards):
        if len(cards) < 3 or len(cards) > 4:
            return False
        
        # Check if all cards have the same value
        return all(card.value == cards[0].value for card in cards)

    def validate_combination(self, cards):
        return self.is_sequence(cards) or self.is_set(cards)

    def declare_combination(self, player, card_ids):
        hand = self.creator_hand if player == 'creator' else self.joiner_hand
        cards = [card for card in hand if card.id in card_ids]
        
        if self.validate_combination(cards):
            self.declared_combinations[player].append(cards)
            # Remove declared cards from hand
            for card in cards:
                hand.remove(card)
            return True
        return False

    def calculate_points(self, cards):
        points = 0
        for card in cards:
            if card.value in ['J', 'Q', 'K']:
                points += 10
            elif card.value == 'A':
                points += 1
            else:
                points += int(card.value)
        return points

    def check_winner(self, player):
        hand = self.creator_hand if player == 'creator' else self.joiner_hand
        if not hand:  # All cards have been declared in valid combinations
            opponent = 'joiner' if player == 'creator' else 'creator'
            opponent_hand = self.joiner_hand if player == 'creator' else self.creator_hand
            
            # Calculate points
            self.points[opponent] += self.calculate_points(opponent_hand)
            self.game_winner = player
            return True
        return False

    def start_game(self):
        # Deal 15 cards to creator and 14 to joiner
        self.creator_hand = [self.deck.pop() for _ in range(15)]
        self.joiner_hand = [self.deck.pop() for _ in range(14)]
        # Put one card in discard pile
        self.discard_pile.append(self.deck.pop())
        self.both_players_joined = True

    def draw_card(self, player):
        if not self.deck:
            # Reshuffle discard pile if deck is empty
            if self.discard_pile:
                last_card = self.discard_pile.pop()
                self.deck = self.discard_pile
                self.discard_pile = [last_card]
                random.shuffle(self.deck)
            else:
                return None

        card = self.deck.pop()
        if player == 'creator':
            self.creator_hand.append(card)
        else:
            self.joiner_hand.append(card)
        return card

    def discard_card(self, player, card_id):
        hand = self.creator_hand if player == 'creator' else self.joiner_hand
        card = next((card for card in hand if card.id == card_id), None)
        
        if card:
            hand.remove(card)
            self.discard_pile.append(card)
            if player == 'creator' and not self.creator_first_discard:
                self.creator_first_discard = True
            self.current_turn = 'joiner' if player == 'creator' else 'creator'
            return True
        return False

def generate_game_code():
    while True:
        # Generate a 6-character code using uppercase letters and numbers
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        # Make sure it's unique
        if code not in active_games:
            return code

def cleanup_game(game_code):
    """Remove the game after 60 seconds if no one joins"""
    time.sleep(60)  # Wait for 60 seconds
    if game_code in active_games:
        game = active_games[game_code]['game']
        if not game.both_players_joined:  # Only remove if game hasn't started
            del active_games[game_code]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create-game', methods=['POST'])
def create_game():
    try:
        game_code = generate_game_code()
        active_games[game_code] = {
            'game': Game(),
            'creator_id': str(uuid.uuid4()),
            'joiner_id': None
        }
        
        # Start cleanup timer in a separate thread
        cleanup_thread = threading.Thread(target=cleanup_game, args=(game_code,))
        cleanup_thread.daemon = True
        cleanup_thread.start()
        
        return jsonify({'success': True, 'code': game_code})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/join-game', methods=['POST'])
def join_game():
    code = request.json.get('code', '').upper()
    if code in active_games and not active_games[code]['joiner_id']:
        active_games[code]['joiner_id'] = str(uuid.uuid4())
        active_games[code]['game'].start_game()
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Invalid game code or game is full'})

@app.route('/check-game-status/<code>')
def check_game_status(code):
    if code not in active_games:
        return jsonify({
            'valid': False,
            'message': 'Game has expired or does not exist'
        })
    
    game_data = active_games[code]
    game = game_data['game']
    
    # Check if the game has timed out
    if not game.both_players_joined and time.time() - game.creation_time > 60:
        del active_games[code]
        return jsonify({
            'valid': False,
            'message': 'Game has expired. No one joined within 60 seconds.'
        })
    
    # Game is considered started when both players are present
    if game.both_players_joined:
        return jsonify({
            'valid': True,
            'started': True
        })
    
    return jsonify({
        'valid': True,
        'started': False,
        'timeLeft': int(60 - (time.time() - game.creation_time))
    })

@app.route('/game/<code>')
def game(code):
    if code not in active_games:
        return redirect('/')
    role = request.args.get('role')
    if role not in ['creator', 'joiner']:
        return redirect('/')
    return render_template('game.html')

@app.route('/game-state/<code>')
def game_state(code):
    if code not in active_games:
        return jsonify({'error': 'Game not found'})

    game = active_games[code]['game']
    is_creator = request.args.get('player') == 'creator'
    
    return jsonify({
        'isMyTurn': game.current_turn == ('creator' if is_creator else 'joiner'),
        'cards': [card.to_dict() for card in (game.creator_hand if is_creator else game.joiner_hand)],
        'topDiscard': game.discard_pile[-1].to_dict() if game.discard_pile else None,
        'mustDiscard': len(game.creator_hand if is_creator else game.joiner_hand) > (15 if is_creator else 14),
        'opponentCardCount': len(game.joiner_hand if is_creator else game.creator_hand),
        'gameStarted': game.both_players_joined,
        'deckCount': len(game.deck),
        'declaredCombinations': game.declared_combinations['creator' if is_creator else 'joiner'],
        'points': game.points['creator' if is_creator else 'joiner'],
        'winner': game.game_winner,
        'creatorFirstDiscard': game.creator_first_discard
    })

@app.route('/draw-card', methods=['POST'])
def draw_card():
    data = request.get_json()
    game_code = data.get('gameCode')
    is_creator = data.get('isCreator')
    from_discard = data.get('fromDiscard', False)

    if game_code not in active_games:
        return jsonify({'success': False, 'error': 'Game not found'})

    game_data = active_games[game_code]
    game = game_data['game']
    player_type = 'creator' if is_creator else 'joiner'

    # Check if it's the player's turn
    if game.current_turn != player_type:
        return jsonify({'success': False, 'error': 'Not your turn'})

    # Check if the player must discard first
    player_hand = game.creator_hand if is_creator else game.joiner_hand
    if len(player_hand) > (15 if is_creator else 14):
        return jsonify({'success': False, 'error': 'Must discard first'})

    if from_discard:
        if not game.discard_pile:
            return jsonify({'success': False, 'error': 'Discard pile is empty'})
        card = game.discard_pile.pop()
        if is_creator:
            game.creator_hand.append(card)
        else:
            game.joiner_hand.append(card)
    else:
        card = game.draw_card(player_type)
        if not card:
            return jsonify({'success': False, 'error': 'No cards left to draw'})

    return jsonify({'success': True})

@app.route('/discard-card', methods=['POST'])
def discard_card():
    data = request.get_json()
    game_code = data.get('gameCode')
    is_creator = data.get('isCreator')
    card_id = data.get('cardId')

    if game_code not in active_games:
        return jsonify({'success': False, 'error': 'Game not found'})

    game = active_games[game_code]['game']
    player_type = 'creator' if is_creator else 'joiner'

    if game.discard_card(player_type, card_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Invalid card'})

@app.route('/declare-combination', methods=['POST'])
def declare_combination():
    data = request.get_json()
    game_code = data.get('gameCode')
    is_creator = data.get('isCreator')
    card_ids = data.get('cardIds')

    if game_code not in active_games:
        return jsonify({'success': False, 'error': 'Game not found'})

    game = active_games[game_code]['game']
    player_type = 'creator' if is_creator else 'joiner'

    if game.declare_combination(player_type, card_ids):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Invalid combination'})

@app.route('/check-winner', methods=['POST'])
def check_winner():
    data = request.get_json()
    game_code = data.get('gameCode')
    is_creator = data.get('isCreator')

    if game_code not in active_games:
        return jsonify({'success': False, 'error': 'Game not found'})

    game = active_games[game_code]['game']
    player_type = 'creator' if is_creator else 'joiner'

    if game.check_winner(player_type):
        return jsonify({'success': True, 'winner': player_type})
    return jsonify({'success': False, 'error': 'Game not over'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)
