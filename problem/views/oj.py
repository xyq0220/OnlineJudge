import random, math
from django.db.models import Q, Count, Max, Sum
from utils.api import APIView
from account.decorators import check_contest_permission
from ..models import ProblemTag, Problem, ProblemRuleType, ProblemTagShip
from ..serializers import ProblemSerializer, TagSerializer, ProblemSafeSerializer
from contest.models import ContestRuleType
import logging


class ProblemTagAPI(APIView):
    def get(self, request):
        qs = ProblemTag.objects
        keyword = request.GET.get("keyword")
        if keyword:
            qs = ProblemTag.objects.filter(name__icontains=keyword)
        tags = qs.annotate(problem_count=Count("problem")).filter(problem_count__gt=0)
        return self.success(TagSerializer(tags, many=True).data)


class PickOneAPI(APIView):
    def get(self, request):
        problems = Problem.objects.filter(contest_id__isnull=True, visible=True)
        count = problems.count()
        if count == 0:
            return self.error("No problem to pick")
        return self.success(problems[random.randint(0, count - 1)]._id)


class ProblemAPI(APIView):
    @staticmethod
    def _add_problem_status(request, queryset_values):
        if request.user.is_authenticated:
            profile = request.user.userprofile
            acm_problems_status = profile.acm_problems_status.get("problems", {})
            oi_problems_status = profile.oi_problems_status.get("problems", {})
            # paginate data
            results = queryset_values.get("results")
            if results is not None:
                problems = results
            else:
                problems = [queryset_values, ]
            for problem in problems:
                if problem["rule_type"] == ProblemRuleType.ACM:
                    problem["my_status"] = acm_problems_status.get(str(problem["id"]), {}).get("status")
                else:
                    problem["my_status"] = oi_problems_status.get(str(problem["id"]), {}).get("status")

    # 按照标签智能推荐
    @staticmethod
    def _tag_based_sort(request, queryset_values):
        tags = request.GET.get("tags")

        # paginate data
        results = queryset_values.get("results")
        if results is not None:
            problems = results
        else:
            problems = [queryset_values, ]
        if tags:
            tags = tags.split(',')
            for problem in problems:
                total_tagged_number = ProblemTagShip.objects.filter(problem__id=problem["id"]).aggregate(Max('tagged_number'))["tagged_number__max"]
                score = 0
                for item in tags:
                    try:
                        tagged_number = ProblemTagShip.objects.get(problem__id=problem["id"], tag__name=item).tagged_number
                    except ProblemTagShip.DoesNotExist:
                        tagged_number = 0
                    tag_users = ProblemTagShip.objects.filter(tag__name=item).aggregate(Sum('tagged_number'))["tagged_number__sum"]
                    score +=1 / (1 + math.log(1 + tag_users)) * tagged_number / (1 + math.log(1 + total_tagged_number))
                problem["tag_score"] = score
            problems.sort(key = lambda problem: problem["tag_score"], reverse = True)


    def get(self, request):
        # 问题详情页
        problem_id = request.GET.get("problem_id")
        if problem_id:
            try:
                problem = Problem.objects.select_related("created_by") \
                    .get(_id=problem_id, contest_id__isnull=True, visible=True)
                problem_data = ProblemSerializer(problem).data
                self._add_problem_status(request, problem_data)
                return self.success(problem_data)
            except Problem.DoesNotExist:
                return self.error("Problem does not exist")

        limit = request.GET.get("limit")
        if not limit:
            return self.error("Limit is needed")

        problems = Problem.objects.select_related("created_by").filter(contest_id__isnull=True, visible=True)
            
        # 搜索的情况
        keyword = request.GET.get("keyword", "").strip()
        if keyword:
            problems = problems.filter(Q(title__icontains=keyword) | Q(_id__icontains=keyword))

        # 难度筛选
        difficulty = request.GET.get("difficulty")
        if difficulty:
            problems = problems.filter(difficulty=difficulty)
        
        # 根据profile 为做过的题目添加标记
        data = self.paginate_data_spec(problems, ProblemSerializer)
        self._tag_based_sort(request, data)
        data = self.cutt_data(request, data)
        self._add_problem_status(request, data)
        # results = data.get("results")
        # if results is not None:
        #     problems = results
        # else:
        #     problems = [data, ]
        # for problem in problems:
        #     logging.error(problem["tag_score"])
        return self.success(data)
    
    def add_tag(self, request):
        data = request.data
        problem_id = data.pop("id")

        try:
            problem = Problem.objects.get(id=problem_id)
        except Problem.DoesNotExist:
            return self.error("Problem does not exist")

        tags = data.pop("tags")
        data["languages"] = list(data["languages"])
        
        for tag in tags:
            try:
                tag = ProblemTag.objects.get(name=tag)
            except ProblemTag.DoesNotExist:
                tag = ProblemTag.objects.create(name=tag)
            problem_tag_ship, _ = ProblemTagShip.objects.get_or_create(problem=problem,tag=tag)
            problem_tag_ship.add_tagged_number()

        return self.success()


class ContestProblemAPI(APIView):
    def _add_problem_status(self, request, queryset_values):
        if request.user.is_authenticated:
            profile = request.user.userprofile
            if self.contest.rule_type == ContestRuleType.ACM:
                problems_status = profile.acm_problems_status.get("contest_problems", {})
            else:
                problems_status = profile.oi_problems_status.get("contest_problems", {})
            for problem in queryset_values:
                problem["my_status"] = problems_status.get(str(problem["id"]), {}).get("status")

    @check_contest_permission(check_type="problems")
    def get(self, request):
        problem_id = request.GET.get("problem_id")
        if problem_id:
            try:
                problem = Problem.objects.select_related("created_by").get(_id=problem_id,
                                                                           contest=self.contest,
                                                                           visible=True)
            except Problem.DoesNotExist:
                return self.error("Problem does not exist.")
            if self.contest.problem_details_permission(request.user):
                problem_data = ProblemSerializer(problem).data
                self._add_problem_status(request, [problem_data, ])
            else:
                problem_data = ProblemSafeSerializer(problem).data
            return self.success(problem_data)

        contest_problems = Problem.objects.select_related("created_by").filter(contest=self.contest, visible=True)
        if self.contest.problem_details_permission(request.user):
            data = ProblemSerializer(contest_problems, many=True).data
            self._add_problem_status(request, data)
        else:
            data = ProblemSafeSerializer(contest_problems, many=True).data
        return self.success(data)
