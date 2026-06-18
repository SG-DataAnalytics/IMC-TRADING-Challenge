from datamodel import OrderDepth, TradingState, Order
from typing import List
import jsonpickle
import pandas as pd

class Product:
    INTARIAN_PEPPER_ROOT = "INTARIAN_PEPPER_ROOT"
    ASH_COATED_OSMIUM = "ASH_COATED_OSMIUM"

class Trader:
    def __init__(self):
        self.LIMIT = {Product.INTARIAN_PEPPER_ROOT: 80,Product.ASH_COATED_OSMIUM: 80 }
        self.params = {Product.ASH_COATED_OSMIUM:{"PIVOT_PRICE" : 10000, "SPREAD" : 4.5,"ORDER_SIZE" : 15}}

    def bid():
        return 3001
    
    def run(self, state: TradingState):
        result = {}
        traderData = state.traderData
        conversions = 0
        product_list = [Product.INTARIAN_PEPPER_ROOT,Product.ASH_COATED_OSMIUM]

        if Product.INTARIAN_PEPPER_ROOT not in state.order_depths and Product.ASH_COATED_OSMIUM not in state.order_depths:
            return result, conversions, traderData
        
        if Product.INTARIAN_PEPPER_ROOT not in state.order_depths and Product.ASH_COATED_OSMIUM in state.order_depths:
            product_list = [Product.ASH_COATED_OSMIUM]
            
        elif Product.INTARIAN_PEPPER_ROOT in state.order_depths and Product.ASH_COATED_OSMIUM not in state.order_depths:
            product_list = [Product.INTARIAN_PEPPER_ROOT]

        if state.traderData is not None and state.traderData != "":
            traderObject = jsonpickle.decode(state.traderData)
        else:
            traderObject = {"fair_value" : 0}

        for p in product_list:
            if p == Product.ASH_COATED_OSMIUM:
                order_depth = state.order_depths[p]
                orders = []
                param = self.params[p]
                Position_lim = self.LIMIT[p]
                Pivot = param['PIVOT_PRICE']
                Spread = param['SPREAD']
                size = param['ORDER_SIZE']

                # ── 1. Position et Cap ───────────────────────────────────────────────
                position = state.position.get(p, 0)
                buy_cap  = Position_lim - position
                sell_cap = Position_lim + position

                # ── 2. Analyse de la dynamique du carnet ──────────────────────────────
                best_bid = max(order_depth.buy_orders.keys())
                best_ask = min(order_depth.sell_orders.keys())
                mid      = (best_bid + best_ask) / 2
                fair_value = (0.65 * mid) + (0.35 * Pivot)

                # ── 3. CALCUL DU SPREAD DYNAMIQUE ────────────────────────────────────
                # # Si le spread actuel du marché est serré, on réduit notre spread pour 
                # # rester compétitif. Si l'imbalance est forte d'un côté, on décale.

                # Formule : - (position / limit) * facteur_agressivité
                skew = (position / Position_lim) * 6 
                if not pd.isna(fair_value):
                    traderObject["fair_value"] = fair_value


                if traderObject["fair_value"] != 0:
                    our_bid = round(traderObject["fair_value"] - Spread + skew)
                    our_ask = round(traderObject["fair_value"] + Spread + skew)

                            # 5. Pennying Intelligent
                            # On ne veut pas être "trop loin" du meilleur prix du carnet pour être exécuté
                            # Mais on ne dépasse jamais notre fair value de base
                    our_bid = min(our_bid, best_bid + 1)
                    our_ask = max(our_ask, best_ask - 1)

                            # Sniping des Asks (Achat) : si un vendeur est sous notre prix cible
                    sorted_asks = sorted(order_depth.sell_orders.items())
                    for ask, vol in sorted_asks:
                        if ask <= our_bid and buy_cap > 0:
                            qty = min(-vol, buy_cap)
                            orders.append(Order(p, ask, qty))
                            buy_cap -= qty
                            position += qty

                            # Sniping des Bids (Vente) : si un acheteur est au dessus de notre prix cible
                    sorted_bids = sorted(order_depth.buy_orders.items(), reverse=True)
                    for bid, vol in sorted_bids:
                        if bid >= our_ask and sell_cap > 0:
                            qty = min(vol, sell_cap)
                            orders.append(Order(p, bid, -qty))
                            sell_cap -= qty
                            position -= qty
                            
                            # Sniping des Bids (Vente) : si un acheteur est au dessus de notre fair_value
                    sorted_bids = sorted(order_depth.buy_orders.items(), reverse=True)
                    for bid, vol in sorted_bids:
                        if bid >= traderObject["fair_value"] and sell_cap > 0:
                            qty = min(vol, sell_cap)
                            orders.append(Order(p, bid, -qty))
                            sell_cap -= qty
                            position -= qty

                            # Sniping des Asks (Achat) : si un vendeur est sous notre fair_value
                    sorted_asks = sorted(order_depth.sell_orders.items())
                    for ask, vol in sorted_asks:
                        if ask <= traderObject["fair_value"] and buy_cap > 0:
                            qty = min(-vol, buy_cap)
                            orders.append(Order(p, ask, qty))
                            buy_cap -= qty
                            position += qty

                            # 7. Placement des ordres passifs (Market Making)
                            # On remplit le reste de notre capacité avec des ordres en attente
                    if buy_cap > 0:
                        qty = min(size,buy_cap)
                        orders.append(Order(p, int(our_bid), qty))
                    if sell_cap > 0:
                        qty = min(size,sell_cap)
                        orders.append(Order(p, int(our_ask), -qty))
                result[p] = orders
            else:
                order_depth = state.order_depths[p]
                position = state.position.get(p, 0)
                orders = []
                # Quantité restante avant d'atteindre la limite
                buy_vol = self.LIMIT[p] - position

                if buy_vol > 0 and order_depth.sell_orders:
                    # On achète au meilleur ask disponible
                    best_ask = min(order_depth.sell_orders.keys())
                    available = -order_depth.sell_orders[best_ask]
                    qty = min(buy_vol, available)
                    orders.append(Order(p, best_ask, qty))
                result[p] = orders

        traderData = jsonpickle.encode(traderObject)

        return result, conversions, traderData