from accounts.models import CustomUser, Course, DeletionRequest, Notification

def pending_counts(request):
    if not request.user.is_authenticated:
        return {}
    
    context = {}
    
    if request.user.user_type == 'ADMIN':
        context['pending_students_count'] = CustomUser.objects.filter(user_type='STUDENT', status='PENDING').count()
        context['pending_teachers_count'] = CustomUser.objects.filter(user_type='TEACHER', status='PENDING').count()
        
        # Pending courses or courses with pending content
        pending_courses = Course.objects.filter(status='PENDING').count()
        # Courses that are PUBLISHED but have unapproved lessons/quizzes/assignments
        courses_with_updates = Course.objects.filter(
            status='PUBLISHED'
        ).filter(
            lessons__is_approved=False
        ).distinct().count()
        
        context['pending_courses_total'] = pending_courses + courses_with_updates
        context['pending_deletions_count'] = DeletionRequest.objects.filter(status='PENDING').count()
        
        # Unread admin notifications
        context['unread_admin_notifs'] = Notification.objects.filter(user=request.user, is_read=False).count()

    elif request.user.user_type == 'TEACHER':
        # Teacher might want to see rejected courses or pending approvals
        context['teacher_pending_approvals'] = Course.objects.filter(teacher=request.user, status='PENDING').count()
        context['teacher_rejected_courses'] = Course.objects.filter(teacher=request.user, status='REJECTED').count()
        context['unread_teacher_notifs'] = Notification.objects.filter(user=request.user, is_read=False).count()

    elif request.user.user_type == 'STUDENT':
        context['unread_student_notifs'] = Notification.objects.filter(user=request.user, is_read=False).count()

    return context
