from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.http import HttpResponse, JsonResponse

from .models import Article, Tag, ArticleTag, NewsletterEdition, NewsletterArticle, Source
from .pipeline.newsletter import generate_edition, render_edition, EDITION_LABELS, VALID_EDITION_TYPES


class DashboardView(View):
    def get(self, request):
        now = timezone.now()
        seven_days_ago = now - timezone.timedelta(days=7)

        context = {
            'total_articles': Article.objects.count(),
            'articles_this_week': Article.objects.filter(ingested_at__gte=seven_days_ago).count(),
            'untagged_count': Article.objects.filter(tagging_method='none').count(),
            'llm_tagged': Article.objects.filter(tagging_method='llm').count(),
            'rules_tagged': Article.objects.filter(tagging_method='rules').count(),
            'sources': Source.objects.all(),
            'recent_editions': NewsletterEdition.objects.order_by('-generated_at')[:5],
            'top_tags': Tag.objects.order_by('-usage_count')[:10],
            'edition_types': EDITION_LABELS,
        }
        return render(request, 'newsletter/dashboard.html', context)


class EditionListView(View):
    def get(self, request):
        editions = NewsletterEdition.objects.order_by('-generated_at')
        edition_type = request.GET.get('type')
        if edition_type in VALID_EDITION_TYPES:
            editions = editions.filter(edition_type=edition_type)

        context = {
            'editions': editions,
            'edition_types': EDITION_LABELS,
            'selected_type': edition_type,
        }
        return render(request, 'newsletter/edition_list.html', context)


class EditionDetailView(View):
    def get(self, request, pk):
        edition = get_object_or_404(NewsletterEdition, pk=pk)
        html_content = render_edition(edition)
        context = {
            'edition': edition,
            'rendered_content': html_content,
        }
        return render(request, 'newsletter/edition.html', context)


class GenerateEditionView(View):
    def post(self, request):
        edition_type = request.POST.get('edition_type') or request.GET.get('type')
        if edition_type not in VALID_EDITION_TYPES:
            return JsonResponse(
                {'error': f'Invalid edition_type. Valid: {VALID_EDITION_TYPES}'},
                status=400,
            )
        try:
            edition = generate_edition(edition_type)
            return redirect('edition-detail', pk=edition.pk)
        except Exception as exc:
            return JsonResponse({'error': str(exc)}, status=500)
