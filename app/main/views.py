from flask import render_template, redirect, url_for, abort, flash, request,\
    current_app, make_response, session, jsonify, send_from_directory
from flask_login import login_required, current_user
from . import main
from .forms import EditProfileForm, EditProfileAdminForm, PostForm,\
    CommentForm
from .. import db
from ..models import Permission, Role, User, Post, Comment, updateproducts, Product, ProductProperty, CartItem
from ..decorators import admin_required, permission_required
from sqlalchemy import event
from sqlalchemy.engine import Engine

# with main.app_context_processor():
#     updateproducts()


@event.listens_for(Engine, "after_cursor_execute")
def log_slow_queries(conn, cursor, statement, parameters, context, executemany):
    duration = context.execution_options.get('timeout', 0)  
    if duration >= current_app.config.get('FLASKY_SLOW_DB_QUERY_TIME', 0.5):
        current_app.logger.warning(
            'Slow query: %s\nParameters: %s\nDuration: %fs\n'
            % (statement, parameters, duration)
        )

@main.after_app_request
def after_request(response):
    return response

# @main.route('/add_to_cart', methods=['POST'])
# def add_to_cart():
#     data = request.json
#     product_name = data.get('product_name')
#     product_price = data.get('product_price')
#     quantity = data.get('quantity', 1)
    
#     # Если корзина еще не создана, создаем её
#     if 'cart' not in session:
#         session['cart'] = {}

#     cart = session['cart']
    
#     if product_name in cart:
#         cart[product_name]['quantity'] += quantity
#     else:
#         cart[product_name] = {'quantity': quantity, 'price': product_price}

#     # Сохраняем изменения в сессии
#     session.modified = True
#     return jsonify({'message': 'Товар добавлен в корзину'})


# @main.route('/remove_from_cart', methods=['POST'])
# def remove_from_cart():
#     data = request.json
#     product_name = data.get('product_name')

#     if 'cart' in session and product_name in session['cart']:
#         del session['cart'][product_name]
#         session.modified = True
#         return jsonify({'message': 'Товар удален из корзины'})
#     return jsonify({'message': 'Товар не найден в корзине'}), 404


# @main.route('/update_cart', methods=['POST'])
# def update_cart():
#     data = request.json
#     product_name = data.get('product_name')
#     quantity = data.get('quantity', 1)

#     if 'cart' in session and product_name in session['cart']:
#         if quantity > 0:
#             session['cart'][product_name]['quantity'] = quantity
#         else:
#             del session['cart'][product_name]
#         session.modified = True
#         return jsonify({'message': 'Корзина обновлена'})
    
#     return jsonify({'message': 'Товар не найден в корзине'}), 404


# @main.route('/get_cart', methods=['GET'])
# def get_cart():
#     if 'cart' not in session:
#         return jsonify({'cart': {}, 'total': 0})

#     cart = session['cart']
#     total = sum(item['price'] * item['quantity'] for item in cart.values())
#     return jsonify({'cart': cart, 'total': total})


@main.route('/laba1/<filename>')
def download_file(filename):
    if filename == "Политика_конфиденциальности.pdf":
        return send_from_directory('static', filename, as_attachment=False)
    return "Файл не найден", 404


@main.route('/<filename>')
def download_file1(filename):
    if filename == "Политика_конфиденциальности.pdf":
        return send_from_directory('static', filename, as_attachment=False)
    return "Файл не найден", 404




@main.route('/shutdown')
def server_shutdown():
    if not current_app.testing:
        abort(404)
    shutdown = request.environ.get('werkzeug.server.shutdown')
    if not shutdown:
        abort(500)
    shutdown()
    return 'Shutting down...'


@main.route('/', methods=['GET', 'POST'])
def index():
    form = PostForm()
    if current_user.can(Permission.WRITE) and form.validate_on_submit():
        post = Post(body=form.body.data,
                    author=current_user._get_current_object())
        db.session.add(post)
        db.session.commit()
        return redirect(url_for('.index'))
    page = request.args.get('page', 1, type=int)
    show_followed = False
    if current_user.is_authenticated:
        show_followed = bool(request.cookies.get('show_followed', ''))
    if show_followed:
        query = current_user.followed_posts
    else:
        query = Post.query
    pagination = query.order_by(Post.timestamp.desc()).paginate(
        page=page, per_page=current_app.config['FLASKY_POSTS_PER_PAGE'],
        error_out=False)
    posts = pagination.items
    return render_template('/lab1/laba1.html', form=form, posts=posts,
                           show_followed=show_followed, pagination=pagination)






@main.route('/laba1')
def laba():
    filtered_products_query = Product.query
    return render_template('/lab1/laba1.html', products=filtered_products_query)

@main.route('/laba1/about_us')
def page1():
    return render_template('/lab1/about_us.html')


@main.route('/laba1/services', methods=['GET'])
def lab1_page2():
    search_query = request.args.get('search', '').lower()  
    category = request.args.get('category', 'all') 


    filtered_products_query = Product.query

    if search_query:

        filtered_products_query = filtered_products_query.filter(
            (Product.name.ilike(f'%{search_query}%')) |
            (Product.alias.ilike(f'%{search_query}%'))
        )

    if category != 'all':
        # Фильтрация по категориям на основе ProductProperty
        category_map = {
            'face': 'Косметика для лица',
            'eyes': 'Косметика для глаз',
            'brows': 'Косметика для бровей'
        }
        category_name = category_map.get(category)

        if category_name:
            filtered_products_query = filtered_products_query.join(ProductProperty).filter(
                ProductProperty.property_name == 'Категория',
                ProductProperty.property_value == category_name
            )


    filtered_products = filtered_products_query.all()

    return render_template('lab1/services.html', products=filtered_products, search_query=search_query, category=category)

@main.route('/laba1/contacts')
def lab1_page3():
    return render_template('/lab1/contacts.html')

@main.route('/laba1/employees')
def lab1_page4():
    return render_template('/lab1/employees.html')

@main.route('/feedback', methods=['GET', 'POST'])
def feedback():
    if request.method == 'POST':
        name = request.form.get('name')
        rating = request.form.get('rating')
        services = request.form.getlist('services')
        feedback = request.form.get('feedback')
        suggestions = request.form.get('suggestions')
        visit_frequency = request.form.get('visit_frequency')
        
        print(f"Отзыв от {name}: {feedback}")
        print(f"Оценка: {rating}, Частота: {visit_frequency}")
        print(f"Услуги: {', '.join(services)}")
        print(f"Предложения: {suggestions}")
        

        Name = User.query.filter_by(username=name).first()
        Name.text = feedback
        db.session.commit()
    

    return render_template('/lab1/feedback.html')


@main.route('/user/<username>')
def user(username):
    user = User.query.filter_by(username=username).first_or_404()
    page = request.args.get('page', 1, type=int)
    pagination = user.posts.order_by(Post.timestamp.desc()).paginate(
        page=page, per_page=current_app.config['FLASKY_POSTS_PER_PAGE'],
        error_out=False)
    posts = pagination.items
    return render_template('user.html', user=user, posts=posts,
                           pagination=pagination)


@main.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm()
    if form.validate_on_submit():
        current_user.name = form.name.data
        current_user.location = form.location.data
        current_user.about_me = form.about_me.data
        db.session.add(current_user._get_current_object())
        db.session.commit()
        flash('Your profile has been updated.')
        return redirect(url_for('.user', username=current_user.username))
    form.name.data = current_user.name
    form.location.data = current_user.location
    form.about_me.data = current_user.about_me
    return render_template('edit_profile.html', form=form)


@main.route('/edit-profile/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_profile_admin(id):
    user = User.query.get_or_404(id)
    form = EditProfileAdminForm(user=user)
    if form.validate_on_submit():
        user.email = form.email.data
        user.username = form.username.data
        user.confirmed = form.confirmed.data
        user.role = Role.query.get(form.role.data)
        user.name = form.name.data
        user.location = form.location.data
        user.about_me = form.about_me.data
        db.session.add(user)
        db.session.commit()
        flash('The profile has been updated.')
        return redirect(url_for('.user', username=user.username))
    form.email.data = user.email
    form.username.data = user.username
    form.confirmed.data = user.confirmed
    form.role.data = user.role_id
    form.name.data = user.name
    form.location.data = user.location
    form.about_me.data = user.about_me
    return render_template('edit_profile.html', form=form, user=user)


@main.route('/cart', methods=['GET'])
@login_required
def get_cart():
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    return jsonify([item.to_dict() for item in items])

@main.route('/cart', methods=['POST'])
@login_required
def add_to_cart():
    data = request.json
    item = CartItem.query.filter_by(user_id=current_user.id, product_name=data['product_name']).first()
    if item:
        item.quantity += data['quantity']
    else:
        item = CartItem(
            user_id=current_user.id,
            product_name=data['product_name'],
            quantity=data['quantity'],
            price=data['price']
        )
        db.session.add(item)
    db.session.commit()
    return jsonify(item.to_dict())

@main.route('/cart/<int:item_id>', methods=['PUT'])
@login_required
def update_cart_item(item_id):
    data = request.json
    item = CartItem.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    item.quantity = data.get('quantity', item.quantity)
    db.session.commit()
    return jsonify(item.to_dict())

@main.route('/cart/<int:item_id>', methods=['DELETE'])
@login_required
def delete_cart_item(item_id):
    item = CartItem.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    db.session.delete(item)
    db.session.commit()
    return jsonify({'success': True})


@main.route('/post/<int:id>', methods=['GET', 'POST'])
def post(id):
    post = Post.query.get_or_404(id)
    form = CommentForm()
    if form.validate_on_submit():
        comment = Comment(body=form.body.data,
                          post=post,
                          author=current_user._get_current_object())
        db.session.add(comment)
        db.session.commit()
        flash('Your comment has been published.')
        return redirect(url_for('.post', id=post.id, page=-1))
    page = request.args.get('page', 1, type=int)
    if page == -1:
        page = (post.comments.count() - 1) // \
            current_app.config['FLASKY_COMMENTS_PER_PAGE'] + 1
    pagination = post.comments.order_by(Comment.timestamp.asc()).paginate(
        page=page, per_page=current_app.config['FLASKY_COMMENTS_PER_PAGE'],
        error_out=False)
    comments = pagination.items
    return render_template('post.html', posts=[post], form=form,
                           comments=comments, pagination=pagination)


@main.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    post = Post.query.get_or_404(id)
    if current_user != post.author and \
            not current_user.can(Permission.ADMIN):
        abort(403)
    form = PostForm()
    if form.validate_on_submit():
        post.body = form.body.data
        db.session.add(post)
        db.session.commit()
        flash('The post has been updated.')
        return redirect(url_for('.post', id=post.id))
    form.body.data = post.body
    return render_template('edit_post.html', form=form)


@main.route('/follow/<username>')
@login_required
@permission_required(Permission.FOLLOW)
def follow(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('Invalid user.')
        return redirect(url_for('.index'))
    if current_user.is_following(user):
        flash('You are already following this user.')
        return redirect(url_for('.user', username=username))
    current_user.follow(user)
    db.session.commit()
    flash('You are now following %s.' % username)
    return redirect(url_for('.user', username=username))


@main.route('/unfollow/<username>')
@login_required
@permission_required(Permission.FOLLOW)
def unfollow(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('Invalid user.')
        return redirect(url_for('.index'))
    if not current_user.is_following(user):
        flash('You are not following this user.')
        return redirect(url_for('.user', username=username))
    current_user.unfollow(user)
    db.session.commit()
    flash('You are not following %s anymore.' % username)
    return redirect(url_for('.user', username=username))


@main.route('/followers/<username>')
def followers(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('Invalid user.')
        return redirect(url_for('.index'))
    page = request.args.get('page', 1, type=int)
    pagination = user.followers.paginate(
        page=page, per_page=current_app.config['FLASKY_FOLLOWERS_PER_PAGE'],
        error_out=False)
    follows = [{'user': item.follower, 'timestamp': item.timestamp}
               for item in pagination.items]
    return render_template('followers.html', user=user, title="Followers of",
                           endpoint='.followers', pagination=pagination,
                           follows=follows)


@main.route('/followed_by/<username>')
def followed_by(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('Invalid user.')
        return redirect(url_for('.index'))
    page = request.args.get('page', 1, type=int)
    pagination = user.followed.paginate(
        page=page, per_page=current_app.config['FLASKY_FOLLOWERS_PER_PAGE'],
        error_out=False)
    follows = [{'user': item.followed, 'timestamp': item.timestamp}
               for item in pagination.items]
    return render_template('followers.html', user=user, title="Followed by",
                           endpoint='.followed_by', pagination=pagination,
                           follows=follows)


@main.route('/all')
@login_required
def show_all():
    resp = make_response(redirect(url_for('.index')))
    resp.set_cookie('show_followed', '', max_age=30*24*60*60)
    return resp


@main.route('/followed')
@login_required
def show_followed():
    resp = make_response(redirect(url_for('.index')))
    resp.set_cookie('show_followed', '1', max_age=30*24*60*60)
    return resp


@main.route('/moderate')
@login_required
@permission_required(Permission.MODERATE)
def moderate():
    page = request.args.get('page', 1, type=int)
    pagination = Comment.query.order_by(Comment.timestamp.desc()).paginate(
        page=page, per_page=current_app.config['FLASKY_COMMENTS_PER_PAGE'],
        error_out=False)
    comments = pagination.items
    return render_template('moderate.html', comments=comments,
                           pagination=pagination, page=page)


@main.route('/moderate/enable/<int:id>')
@login_required
@permission_required(Permission.MODERATE)
def moderate_enable(id):
    comment = Comment.query.get_or_404(id)
    comment.disabled = False
    db.session.add(comment)
    db.session.commit()
    return redirect(url_for('.moderate',
                            page=request.args.get('page', 1, type=int)))


@main.route('/moderate/disable/<int:id>')
@login_required
@permission_required(Permission.MODERATE)
def moderate_disable(id):
    comment = Comment.query.get_or_404(id)
    comment.disabled = True
    db.session.add(comment)
    db.session.commit()
    return redirect(url_for('.moderate',
                            page=request.args.get('page', 1, type=int)))
